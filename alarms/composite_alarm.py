from typing import List

from alarms.alarm import AlarmSender


class CompositeAlarmSender(AlarmSender):
    def __init__(self, all_senders: List[AlarmSender]):
        self.all_senders = []

        for sender in all_senders:
            self.all_senders.append(sender)

    def add_sender(self, sender: AlarmSender):
        self.all_senders.append(sender)

    def push_alarm(self, message: str, severity='alarm'):
        for sender in self.all_senders:
            sender.push_alarm(message, severity)
