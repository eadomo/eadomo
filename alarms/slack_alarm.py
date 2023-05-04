import logging
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from alarms.alarm import AlarmSender, AlarmSeverity


class SlackAlarmSender(AlarmSender):
    def __init__(self):
        self.enabled = True

        self.SLACK_TOKEN = os.getenv('SLACK_TOKEN')
        if not self.SLACK_TOKEN:
            logging.error('SLACK_TOKEN not set - slack alarms disabled')
            self.enabled = False
            return

        self.SLACK_CHAT = os.getenv('SLACK_CHAT')
        if not self.SLACK_CHAT:
            logging.error('SLACK_CHAT not set - slack alarms disabled')
            self.enabled = False
            return

        self.ENV_NAME = os.getenv('ENV_NAME')
        if not self.ENV_NAME:
            logging.error('ENV_NAME not set')
            raise EnvironmentError()

    def push_alarm(self, message: str, severity: AlarmSeverity = AlarmSeverity.ALARM):
        if self.enabled:
            message = severity.value.upper() + ": " + message
            logging.debug(f"sending slack message [{message}]")

            client = WebClient(token=self.SLACK_TOKEN)
            try:
                client.chat_postMessage(channel="#" + self.SLACK_CHAT, text=message)
            except SlackApiError as e:
                logging.error(f"error: {e.response['error']}")
