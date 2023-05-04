import datetime
import logging

from pymongo import MongoClient

from alarms.alarm import AlarmSender, AlarmSeverity


class RestartNotificationManager:
    MONGO_COLLECTION_NAME = 'restart_notifications'

    def __init__(self, mongo_db: MongoClient, alarm_sender: AlarmSender):
        self.mongo_db = mongo_db
        self.alarm_sender = alarm_sender
        self.mongo_collection = self.mongo_db[RestartNotificationManager.MONGO_COLLECTION_NAME]
        self.mongo_collection.create_index(
                [
                    ('valid_from', -1),
                    ('valid_until', -1),
                    ('affected_object', 1),
                    ('object_type', 1)
                ])

    def check_notification_present(self, affected_obj: str, obj_type: str, time: datetime.datetime):
        find_filter = {
            'valid_from': {'$lte': time},
            'valid_until': {'$gte': time},
            'affected_object': {'$eq': affected_obj},
            'object_type': {'$eq': obj_type},
        }
        notification = self.mongo_collection.find_one(filter=find_filter)

        return notification is not None

    def add_notification(self, affected_obj: str, obj_type: str,
                         time_from: datetime.datetime, time_to: datetime.datetime):
        rec = {
            "creation_time": datetime.datetime.now(),
            "affected_object": affected_obj,
            "object_type": obj_type,
            "valid_from": time_from,
            "valid_until": time_to
        }
        self.mongo_collection.insert_one(rec)

        message = f"{obj_type} {affected_obj} " \
                  f"is scheduled to be restarted between {time_from} and {time_to}"

        logging.info(message)

        self.alarm_sender.push_alarm(message, AlarmSeverity.INFO)

    def list_notifications(self, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_collection.find({'creation_time': {'$gt': time_from}}, {
            '_id': 0}, limit=100, sort=[('timestamp', -1)]))
