import datetime
import logging
from enum import Enum
from abc import ABC, abstractmethod
from typing import Optional

from alarms.alarm import AlarmSeverity
from alarms.alarm import AlarmSender
from utils.restart_notification_manager import RestartNotificationManager


class OverallStatusAccumulator:
    def __init__(self):
        self.all_ok = True

    def fail(self):
        self.update_status(False)

    def update_status(self, is_ok):
        if not is_ok:
            self.all_ok = False

    def is_ok(self):
        return self.all_ok

    def reset_status(self):
        self.all_ok = True


class AbstractCheck(ABC):
    class CheckResult(Enum):
        NEGATIVE = 0
        POSITIVE = 1
        NON_BINARY = 2
        MISSING = 3  # not result yet
        EXEC_FAILURE = 4  # execution failure, not a result
        NOT_SUPPORTED = 5

    DEFAULT_RESEND_THRESHOLD = 600  # notification resent interval, in seconds
    DEFAULT_CHECK_REPEAT_INTERVAL = 60  # check repeat interval, in seconds

    def __init__(self,
                 obj_name: str,  # object the checker is attached to
                 status_acc: OverallStatusAccumulator,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = DEFAULT_RESEND_THRESHOLD):
        self.obj_name = obj_name
        self.status_acc = status_acc
        self.check_repeat_interval = check_repeat_interval
        self.last_execution_time: Optional[datetime.datetime] = None
        self.last_status: AbstractCheck.CheckResult = AbstractCheck.CheckResult.MISSING
        self.last_status_change: Optional[datetime.date] = None
        self.last_notification_sent_timestamp: Optional[datetime.date] = None
        self.resend_threshold: int = resend_threshold
        self.alarm_sender: AlarmSender = alarm_sender
        self.restart_notification_manager = restart_notification_manager
        self.last_return_value = None

    @abstractmethod
    def do_check(self, **kwargs):
        pass

    def shall_repeat(self):
        if self.check_repeat_interval is None:
            return True

        if self.last_execution_time is None:
            return True

        return datetime.datetime.now() - self.last_execution_time > \
               datetime.timedelta(seconds=self.check_repeat_interval)

    def get_last_status(self):
        return self.last_status

    def _set_status(self, status):
        if self.last_status != status:
            self.last_status_change = datetime.datetime.now()

        self.last_status = status

    def _update_exec_time(self):
        self.last_execution_time = datetime.datetime.now()

    def signal_notification_sent(self):
        self.last_notification_sent_timestamp = datetime.datetime.now()

    def has_status_changed_after_last_notification(self):
        if self.last_status_change is None:
            return False
        if self.last_notification_sent_timestamp is None:
            return True
        return self.last_notification_sent_timestamp < self.last_status_change

    def should_send_notification(self):
        if self.last_notification_sent_timestamp is None:
            return self.has_status_changed_after_last_notification()

        return self.has_status_changed_after_last_notification() \
            or datetime.datetime.now() - self.last_notification_sent_timestamp > \
            datetime.timedelta(seconds=self.resend_threshold)

    def _send_smart_alarm(self, message, severity=AlarmSeverity.ALARM):
        if self.alarm_sender and self.should_send_notification():
            self.alarm_sender.push_alarm(message, severity)
            self.signal_notification_sent()

    def _report_check(self):
        logging.debug(f"running check {self.__class__.__name__} for \"{self.obj_name}\"; "
                      f"last executed: {self.last_execution_time if self.last_execution_time else '-'}; "
                      f"current status: {self.status_acc.is_ok()}")
