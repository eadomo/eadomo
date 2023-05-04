from enum import Enum
from abc import ABC, abstractmethod


class AlarmSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ALARM = "alarm"


class AlarmSender(ABC):
    @abstractmethod
    def push_alarm(self, message, severity: AlarmSeverity = AlarmSeverity.ALARM):
        pass
