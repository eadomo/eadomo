import logging
import tempfile
from typing import Callable, Optional, List

import datetime
import tarfile

import jmxquery

import docker
import docker.errors

from alarms.alarm import AlarmSeverity, AlarmSender
from checkers.abstract_checker import AbstractChecker
from checkers.check import AbstractCheck, OverallStatusAccumulator
from utils.restart_notification_manager import RestartNotificationManager

logging.getLogger("jmxquery").setLevel(logging.INFO)

JMX_AGENT_IMAGE = "docker_env_checker_jmx_agent"
JMX_AGENT_PORT = 61234


def java_timestamp_to_datetime(java_timestamp):
    seconds = java_timestamp / 1000
    sub_seconds = (java_timestamp % 1000.0) / 1000.0
    date_time = datetime.datetime.fromtimestamp(seconds + sub_seconds)
    return date_time


class MyJMXConnection(jmxquery.JMXConnection):
    def __init__(self, target_container,
                 jmx_username=None, jmx_password=None):
        super().__init__(
            f"service:jmx:rmi:///jndi/rmi://localhost:{JMX_AGENT_PORT}/jmxrmi",
            jmx_username, jmx_password)
        self.target_container = target_container

    def query(self, queries: List[jmxquery.JMXQuery], timeout=jmxquery.DEFAULT_JAR_TIMEOUT) -> List[jmxquery.JMXQuery]:
        return self._run_remote_jar(queries, timeout)

    def _run_remote_jar(self, queries: List[jmxquery.JMXQuery], timeout) -> List[jmxquery.JMXQuery]:
        container_jar_path = '/opt/jmxquery/jmxquery-0.6.0/jmxquery/JMXQuery-0.1.8.jar'

        command = [self.java_path, '-jar', container_jar_path, '-url', self.connection_uri, "-json"]
        if self.jmx_username:
            command.extend(["-u", self.jmx_username, "-p", self.jmx_password])

        query_string = ""
        for query in queries:
            query_string += query.to_query_string() + ";"

        command.extend(["-q", query_string])
        logging.debug("Running command: " + str(command))

        try:
            (exit_code, (stdout, stderr)) = self.target_container.exec_run(command, demux=True)
            if exit_code != 0:
                logging.error(f"JMX called failed: {stderr}")
                raise RuntimeError()

            json_output = stdout.decode('utf-8')
        except docker.errors.APIError as err:
            logging.error(f"Error calling JMX: {err}")
            raise err

        # noinspection PyUnresolvedReferences
        metrics = self._JMXConnection__load_from_json(json_output)
        return metrics


class CheckJmx(AbstractCheck):

    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 service: dict,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.service = service

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        service = self.service

        jmx_connection = kwargs.get("jmx_connection")

        mbeans = service.get('mbeans', [])
        timeout = int(service.get('timeout', '60'))
        queries = []
        mbeans_dicts = CheckJmx._get_default_jmx_metrics()
        for mbean in mbeans:
            mbean_name = mbean['name']
            our_alias = mbean['our-alias']
            metric_name = mbean.get('metric-name', None)
            metric_labels = mbean.get('metric-labels', None)
            attribute = mbean.get('attribute', None)
            attribute_key = mbean.get('attribute-key', None)
            conv = mbean.get('conv', None)
            conv_func: Optional[Callable[[object]: object]]
            if conv is not None:
                conv_func = eval(f"lambda x : {conv}")
            else:
                conv_func = None
            mbeans_dicts.append({
                'mbean_name': mbean_name,
                'our_alias': our_alias,
                'metric_name': metric_name,
                'metric_labels': metric_labels,
                'attribute': attribute,
                'attribute_key': attribute_key,
                'conv': conv_func,
                'type': 'user'
            })

        for mbean_desc in mbeans_dicts:
            query = jmxquery.JMXQuery(mbean_desc['mbean_name'],
                                      metric_name=mbean_desc.get('metric_name', None),
                                      metric_labels=mbean_desc.get('metric_labels', None),
                                      attribute=mbean_desc.get('attribute', None),
                                      attributeKey=mbean_desc.get('attribute_key', None))
            queries.append(query)

        try:
            metrics = jmx_connection.query(queries, timeout=timeout)
        except (docker.errors.APIError, RuntimeError):
            self.last_return_value = None
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            return self.last_return_value
        metrics_dicts = []
        for metric in metrics:
            our_bean_desc = None
            for requested_mbean in mbeans_dicts:
                if requested_mbean['mbean_name'] != metric.mBeanName:
                    continue
                if requested_mbean.get('metric_name', None) is not None and \
                        metric.metric_name != requested_mbean['metric_name']:
                    continue
                if requested_mbean.get('attribute', None) is not None and \
                        metric.attribute != requested_mbean['attribute']:
                    continue
                if requested_mbean.get('attribute_key', None) is not None and \
                        metric.attributeKey != requested_mbean['attribute_key']:
                    continue
                our_bean_desc = requested_mbean
                break
            if our_bean_desc is None:
                continue

            value = metric.value
            conv: Callable[[Optional[object]], object]
            conv = our_bean_desc.get('conv', None)
            if conv is not None:
                value = conv(value)

            metrics_dicts.append({
                'our_alias': our_bean_desc['our_alias'],
                'mbean_name': metric.mBeanName,
                'metric_name': metric.metric_name,
                'metric_labels': metric.metric_labels,
                'attribute': metric.attribute,
                'attribute_key': metric.attributeKey,
                'value_type': metric.value_type,
                'value': value,
                'type': our_bean_desc['type']
            })
        stat_dict = {}
        user_dict = {}
        for metric in metrics_dicts:
            if metric['type'] == 'stat':
                stat_dict[metric['our_alias']] = metric['value']
            elif metric['type'] == 'user':
                user_dict[metric['our_alias']] = metric['value']
        self.last_return_value = (stat_dict, user_dict)
        self._set_status(AbstractCheck.CheckResult.NON_BINARY)
        return self.last_return_value

    @staticmethod
    def _get_default_jmx_metrics():
        return [
            {
                'our_alias': 'memory_usage_bytes',
                'mbean_name': 'java.lang:type=Memory',
                'metric_name': 'HeapMemoryUsage',
                'attribute': 'HeapMemoryUsage',
                'attribute_key': 'used',
                'type': 'stat'
            },
            {
                'our_alias': 'cpu_usage_percent',
                'mbean_name': 'java.lang:type=OperatingSystem',
                'metric_name': 'ProcessCpuLoad',
                'attribute': 'ProcessCpuLoad',
                'conv': lambda x: x * 100.0,
                'type': 'stat'
            },
            {
                'our_alias': 'num_threads',
                'mbean_name': 'java.lang:type=Threading',
                'metric_name': 'ThreadCount',
                'attribute': 'ThreadCount',
                'type': 'stat'
            },
            {
                'our_alias': 'num_classes',
                'mbean_name': 'java.lang:type=ClassLoading',
                'metric_name': 'LoadedClassCount',
                'attribute': 'LoadedClassCount',
                'type': 'stat'
            },
            {
                'our_alias': 'uptime_seconds',
                'mbean_name': 'java.lang:type=Runtime',
                'metric_name': 'Uptime',
                'attribute': 'Uptime',
                'type': 'stat',
                'conv': lambda x: x / 1000.0
            },
            {
                'our_alias': 'started_at',
                'mbean_name': 'java.lang:type=Runtime',
                'metric_name': 'StartTime',
                'attribute': 'StartTime',
                'type': 'stat',
                'conv': lambda x: java_timestamp_to_datetime(x)
            }
        ]


class CheckIfRestarted(AbstractCheck):
    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 prev_inventory,
                 restart_notification_manager: RestartNotificationManager,
                 alarm_sender: AlarmSender):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager)
        self.prev_inventory = prev_inventory

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.NEGATIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        name = self.obj_name
        stat_dict = kwargs.get("stat_dict")

        self._update_exec_time()

        started_at = stat_dict.get('started_at', None)

        if self.prev_inventory is not None:
            if name in self.prev_inventory:
                prev_cont = self.prev_inventory[name]
                prev_started_at = prev_cont['started_at']
                if prev_started_at != started_at:
                    planned = self.restart_notification_manager.check_notification_present(
                        name, 'jmx', datetime.datetime.now())
                    severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                    planned = 'as planned' if planned else 'UNPLANNED'

                    self._set_status(AbstractCheck.CheckResult.POSITIVE)

                    logging.warning(f"{name} restarted ({planned})")

                    self._send_smart_alarm(f"JMX service {name} "
                                           f"has been restarted at {started_at} ({planned})",
                                           severity)
                    self.status_acc.fail()
                    self.last_return_value = True
                    return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.NEGATIVE)
        self.last_return_value = False
        return self.last_return_value


class JmxChecker(AbstractChecker):
    CHECK_JMX = "check_jmx"
    CHECK_SERVICE_RESTARTED = "check_service_restarted"

    def __init__(self, config, mongo_db, dockers_pool, alarm_sender, restart_notification_manager):
        self.prev_jmx_status = {}
        self.prev_inventory = None
        self.jmx_connections = {}
        self.stop_flag = False
        self.config = config
        self.mongo_db = mongo_db
        self.dockers_pool = dockers_pool
        self.alarm_sender = alarm_sender
        self.restart_notification_manager = restart_notification_manager
        self.checks = {}
        self.status_acc = {}

        for service in self.config.get('jmx', []):
            if self.stop_flag:
                return
            service_name = service['service']
            serv_checks = {}
            status_acc = OverallStatusAccumulator()
            self.status_acc[service_name] = status_acc
            self.checks[service_name] = serv_checks

            serv_checks[JmxChecker.CHECK_JMX] = \
                CheckJmx(
                    service_name,
                    status_acc,
                    service,
                    self.alarm_sender,
                    self.restart_notification_manager)

            serv_checks[JmxChecker.CHECK_SERVICE_RESTARTED] = \
                CheckIfRestarted(
                    service_name,
                    status_acc,
                    service,
                    self.alarm_sender,
                    self.restart_notification_manager)

        mongo_db['jmx_status'].create_index([('timestamp', -1)])

        self._build_jmx_agent_image()

        last_status = mongo_db['jmx_status'].find_one(sort=[('timestamp', -1)])
        if last_status:
            for obj_name in last_status.get('status', {}):
                if obj_name in self.prev_jmx_status:
                    if 'status' in last_status['status'][obj_name]:
                        self.prev_jmx_status[obj_name]['status'] = last_status['status'][obj_name]['status']

    def request_stop(self):
        self.stop_flag = True

    def check(self):
        jmx_cfg = self.config.get('jmx', None)
        if jmx_cfg is None:
            return
        inventory = {}
        proxy_cont = None
        for service in jmx_cfg:
            if self.stop_flag:
                return
            service_name = service['service']
            logging.debug(f"loading JMX metrics for service {service_name}")

            checks = self.checks[service_name]
            status_acc = self.status_acc[service_name]
            status_acc.reset_status()

            url = service['url']
            url_docker = url.get('docker', None)
            access_url = None
            docker_client = self._get_docker_client_for_service(service)
            if docker_client is None:
                logging.warning(f"docker client not yet available for {service_name}")
            if url_docker and docker_client:
                port = url_docker['port']
                target_container = url_docker['container']
                proxy_name = target_container + "-docker-env-checker-jmxproxy"
                try:
                    proxy_cont = docker_client.containers.get(proxy_name)
                except docker.errors.NotFound:
                    proxy_cont = docker_client.containers.run(
                        JMX_AGENT_IMAGE,
                        f"socat tcp-listen:{JMX_AGENT_PORT},fork,reuseaddr tcp-connect:{target_container}:{port}",
                        name=proxy_name,
                        detach=True,
                        remove=True,
                        network_mode=f"container:{target_container}")

                access_url = f"pass-through-to-{proxy_name}"
            else:
                url_direct = url.get('direct', None)
                if url_direct:
                    access_url = url_direct
            jmx_connection = None
            if access_url:
                if self.jmx_connections and access_url in self.jmx_connections:
                    jmx_connection = self.jmx_connections[access_url]
                else:
                    if url_docker:
                        jmx_connection = MyJMXConnection(proxy_cont)
                    else:
                        jmx_connection = jmxquery.JMXConnection(access_url)
                    self.jmx_connections[access_url] = jmx_connection
            stat_dict = None
            user_dict = None
            if jmx_connection:
                jmx_ret = checks[JmxChecker.CHECK_JMX].do_check(jmx_connection=jmx_connection)
                if jmx_ret:
                    (stat_dict, user_dict) = jmx_ret

            cont = inventory[service_name] = {
                'stats': stat_dict,
                'started_at': stat_dict.get('started_at', None),
                'user_defined': user_dict,
                'status': 'OK'  # TODO
            }

            if stat_dict:
                checks[JmxChecker.CHECK_SERVICE_RESTARTED].do_check(stat_dict=stat_dict)

            if status_acc.is_ok():
                logging.debug('all OK')

            service_status = 'OK' if status_acc.is_ok() else 'NOK'

            if service_name not in self.prev_jmx_status:
                self.prev_jmx_status[service_name] = {'status': service_status}
                if service.get('desc', None):
                    self.prev_jmx_status[service_name]['desc'] \
                        = service['desc']
                if service.get('panel', None):
                    self.prev_jmx_status[service_name]['panel'] \
                        = service['panel']
                if service.get('src', None):
                    self.prev_jmx_status[service_name]['src'] \
                        = service['src']

            if service_name in self.prev_jmx_status and \
                    service_status != self.prev_jmx_status[service_name]['status']:
                if service_status == 'OK':
                    logging.info(f"container {service_name} has been repaired")
                    self.alarm_sender.push_alarm(f"container {service_name} is OK again", AlarmSeverity.INFO)
                else:
                    planned = self.restart_notification_manager.check_notification_present(
                        service_name, 'jmx', datetime.datetime.now())
                    severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                    planned = 'as planned' if planned else 'UNPLANNED'

                    logging.warning(f"service {service_name} is BROKEN ({planned})")
                    self.alarm_sender.push_alarm(f"container {service_name} is BROKEN ({planned})", severity)

            self.prev_jmx_status[service_name]['status'] = service_status
            if service_status != 'OK':
                self.prev_jmx_status[service_name]['last_failure'] \
                    = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if cont:
                self.prev_jmx_status[service_name]['stats'] = cont['stats']
                self.prev_jmx_status[service_name]['user_defined'] = cont['user_defined']

        self.prev_inventory = inventory

    def store_status(self):
        if self.mongo_db is None:
            return

        rec = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            'status': self.prev_jmx_status
        }

        self.mongo_db['jmx_status'].insert_one(rec)

    def get_status(self):
        return self.prev_jmx_status

    def get_stats_for_service(self, service, stat, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['jmx_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{service}.stats.{stat}': 1},
                                                           sort=[('timestamp', 1)]))

    def get_user_defined_param_for_service(self, service, user_defined_param_name, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['jmx_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{service}.user_defined.{user_defined_param_name}': 1},
                                                           sort=[('timestamp', 1)]))

    def get_status_timeseries_for_service(self, service, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['jmx_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{service}.status': 1},
                                                           sort=[('timestamp', 1)]))

    def get_status_timeseries(self, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['jmx_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, 'status.$': 1},
                                            sort=[('timestamp', 1)]))

    def _build_jmx_agent_image(self):
        jmx_cfg = self.config.get('jmx', None)
        if jmx_cfg is None:
            return

        for service in jmx_cfg:
            if self.stop_flag:
                return

            docker_client = self._get_docker_client_for_service(service)

            JmxChecker._build_jmx_agent_image_int(docker_client)

    @staticmethod
    def _build_jmx_agent_image_int(docker_client):
        logging.debug("building JMX agent image")

        with tempfile.TemporaryFile() as build_context:
            with tarfile.open(fileobj=build_context, mode="w") as tar:
                tar.add(name="Dockerfile_jmx_agent", arcname="Dockerfile")
                tar.add("JMXQuery-0.1.8.jar")

            build_context.seek(0, 0)

            try:
                if docker_client:
                    docker_client.images.build(
                        fileobj=build_context,
                        custom_context=True,
                        tag=f"{JMX_AGENT_IMAGE}:latest")
            except docker.errors.DockerException as e:
                logging.error(f"failed to build JMX agent image {e}")

    def _get_docker_client_for_service(self, cont_config):
        docker_id = cont_config.get('docker', None)

        if docker_id is None:
            return self.dockers_pool.get_default_client()

        if self.dockers_pool.has_client_with_id(docker_id):
            # client can be None if it could not be loaded yet
            return self.dockers_pool.get_client_for_id(docker_id)

        raise ValueError(f"docker id {docker_id} is not defined")
