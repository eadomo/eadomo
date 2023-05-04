from abc import ABC, abstractmethod


class AbstractChecker(ABC):
    @abstractmethod
    def store_status(self):
        pass

    @abstractmethod
    def get_status(self):
        pass

    @abstractmethod
    def check(self):
        pass

    @abstractmethod
    def request_stop(self):
        pass

    @abstractmethod
    def get_status_timeseries(self, time_from=None):
        pass
