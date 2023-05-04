import logging
import os

import requests
from alarms.alarm import AlarmSender, AlarmSeverity


class TelegramAlarmSender(AlarmSender):
    def __init__(self):
        self.enabled = True

        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        if not self.TELEGRAM_TOKEN:
            logging.error('TELEGRAM_TOKEN not set - telegram alarms disabled')
            self.enabled = False
            return

        self.TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
        if not self.TELEGRAM_CHAT_ID:
            logging.error('TELEGRAM_CHAT_ID not set - telegram alarms disabled')
            self.enabled = False
            return

        self.ENV_NAME = os.getenv('ENV_NAME')
        if not self.ENV_NAME:
            logging.error('ENV_NAME not set')
            raise EnvironmentError()

    def push_alarm(self, message: str, severity: AlarmSeverity = AlarmSeverity.ALARM):
        if self.enabled:
            message = severity.value.upper() + ": " + message
            logging.debug(f"sending telegram message [{message}]")
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/" \
                  f"sendMessage?chat_id={self.TELEGRAM_CHAT_ID}&text={self.ENV_NAME +' : '+message}"
            resp = requests.get(url, timeout=120)
            if resp.status_code > 205 or not resp.json()['ok']:
                logging.error(f"telegram request failed: {resp.content.decode('utf-8')}")
