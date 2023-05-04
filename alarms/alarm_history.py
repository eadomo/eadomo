import datetime

from alarms.alarm import AlarmSender, AlarmSeverity


class AlarmHistory(AlarmSender):
    def __init__(self, mongo_db):
        self.mongo_db = mongo_db
        self.mongo_db['history'].create_index([('timestamp', -1)])

    def push_alarm(self, message, severity: AlarmSeverity = AlarmSeverity.ALARM):
        self._add_to_history_log(message, severity)

    def _add_to_history_log(self, message, severity: AlarmSeverity):
        rec = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            'message': message,
            'severity': severity.value
        }
        self.mongo_db['history'].insert_one(rec)

    def get_log(self, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['history'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0}, limit=100, sort=[('timestamp', -1)]))
