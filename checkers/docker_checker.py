import logging
import datetime
import os
import traceback
from typing import Optional
import re

import dateutil.parser
import docker
import docker.errors

from alarms.alarm import AlarmSeverity, AlarmSender
from checkers.abstract_checker import AbstractChecker
from checkers.check import AbstractCheck, OverallStatusAccumulator
from utils.git_tools import has_diff_between_two_branches
from utils.dockers_pool import DockersPool
from utils.restart_notification_manager import RestartNotificationManager


class CheckFreeDiskSpace(AbstractCheck):
    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 mount_points_thresholds: dict = None,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.mount_points_thresholds = mount_points_thresholds if mount_points_thresholds else {}
        self.default_disk_usage_threshold = float(os.getenv("DEFAULT_DISK_USAGE_THRESHOLD", "80"))

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        docker_client = kwargs.get('docker_client')
        local_source = kwargs.get('local_source')

        self._update_exec_time()

        if not docker_client:
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value

        try:
            logs = docker_client.containers.run("busybox:latest",
                                                "df -P /dir_to_check",
                                                remove=True,
                                                volumes={local_source: {'bind': '/dir_to_check', 'mode': 'ro'}})
            logs = logs.decode('utf-8').split("\n")[1]
            logs = logs.split()
            mount_point = logs[0]
            total_bytes = int(logs[1]) * 1024
            used_bytes = int(logs[2]) * 1024
            usage_percentage = 100.0 * used_bytes / total_bytes if total_bytes > 0 else None
            self.last_return_value = {
                'mount_point': mount_point,
                'total_bytes': total_bytes,
                'used_bytes': used_bytes,
                'usage_percentage': usage_percentage
            }
            if usage_percentage is not None and self.is_disk_usage_too_high(mount_point, usage_percentage):
                logging.warning(f"{self.obj_name} disk {mount_point} usage is too high ({usage_percentage:.2f}%)")

                self._set_status(AbstractCheck.CheckResult.NEGATIVE)

                self._send_smart_alarm(
                    f"container {self.obj_name} disk {mount_point} "
                    f"usage is too high ({usage_percentage:.2f}%)",
                    AlarmSeverity.ALARM)

                self.status_acc.fail()
            else:
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
            return self.last_return_value
        except docker.errors.APIError as error:
            logging.error(f"failed to retrieve disk space: {str(error)}")
        except OSError as error:
            logging.error(f"failed to retrieve disk space: {str(error)}")
        except docker.errors.DockerException as error:
            logging.error(f"failed to retrieve disk space: {str(error)}")

        self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
        self.last_return_value = None
        return self.last_return_value

    def is_disk_usage_too_high(self, mount_point, usage_percentage):
        threshold = self.mount_points_thresholds.get(mount_point, self.default_disk_usage_threshold)

        if usage_percentage > threshold:
            return True

        return False


class CheckIfImageUpdateIsAvailable(AbstractCheck):
    DEFAULT_REPO_SCAN_INTERVAL = 10  # minutes

    def __init__(self, obj_name: str, status_acc: OverallStatusAccumulator, alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 repo_scan_interval: Optional[int] = None):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager)
        self.last_repo_scan = None
        self.repo_scan_interval_minutes = \
            CheckIfImageUpdateIsAvailable.DEFAULT_REPO_SCAN_INTERVAL \
                if repo_scan_interval is None \
                else repo_scan_interval

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            return self.last_return_value

        self._report_check()

        cont = kwargs.get('container')
        cont_config = kwargs.get('cont_config')

        self._update_exec_time()

        now = datetime.datetime.now()

        do_repo_scan = self.last_repo_scan is None or \
                       self.repo_scan_interval_minutes is None or \
                       (now - self.last_repo_scan > datetime.timedelta(minutes=self.repo_scan_interval_minutes))
        if not do_repo_scan:
            if self.get_last_status() == AbstractCheck.CheckResult.POSITIVE:
                self.last_return_value = True
                return self.last_return_value
            if self.get_last_status() == AbstractCheck.CheckResult.NEGATIVE:
                self.last_return_value = False
                return self.last_return_value
            self.last_return_value = None
            return self.last_return_value

        self.last_repo_scan = now

        #   YAML schema
        #     image-update-check:  # optional
        #       image-tag-pattern: main-[0-9a-fA-F]{8}-snapshot  # optional
        #       username: dockermon_access
        #       password: fybyvYiiMxnaSrrmtNxo

        docker_client = cont.client

        update_available = None
        # image_tag = cont.image.tags[0]
        # image_id = cont.image.id
        image_attrs = cont.image.attrs
        if len(image_attrs['RepoDigests']) == 0:
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = False
            return self.last_return_value
        cur_idx = 0
        for image_tag in image_attrs['RepoTags']:
            if cur_idx >= len(image_attrs.get('RepoDigests', [])):
                self._set_status(AbstractCheck.CheckResult.NEGATIVE)
                self.last_return_value = False
                return self.last_return_value
            (source_repo, image_id) = image_attrs['RepoDigests'][cur_idx].split('@')
            cur_idx += 1
            image_created_at = dateutil.parser.parse(image_attrs['Created'])
            try:
                image_check_config = cont_config.get('image-update-check', cont_config.get('update-check', {}))
                auth_config = image_check_config if image_check_config else None
                if auth_config and ('username' not in auth_config or 'password' not in auth_config):
                    auth_config = None
                image_tag_pattern = image_check_config.get('image-tag-pattern', None)
                if image_tag_pattern is None:
                    # just check if image digest has changed
                    try:
                        registry_data = docker_client.images.get_registry_data(image_tag, auth_config=auth_config)
                        if registry_data.id != image_id:
                            logging.debug(f"update available for image {image_tag}")
                            self._set_status(AbstractCheck.CheckResult.POSITIVE)
                            self.last_return_value = True
                            return self.last_return_value
                        update_available = False
                    except docker.errors.APIError as error:
                        logging.error(f"failed to check for newer image: {str(error)}")
                else:
                    # instead of checking a particular image, let's check
                    # if newer images matching the pattern are available
                    image_tag_pattern_compiled = re.compile(image_tag_pattern)
                    image_list = docker_client.images.list(source_repo)
                    for image in image_list:
                        take_image = False
                        for repo_tag in image.tags:
                            tag = repo_tag.split(':')[1]
                            if image_tag_pattern_compiled.match(tag):
                                take_image = True
                                break
                        if not take_image:
                            continue
                        created_at = dateutil.parser.parse(image.attrs['Created'])
                        if created_at > image_created_at:
                            self._set_status(AbstractCheck.CheckResult.POSITIVE)
                            self.last_return_value = True
                            return self.last_return_value
                    if update_available is None:
                        update_available = False
            except docker.errors.APIError as err:
                if err.status_code == 429:
                    logging.warning("too many requests to docker registry, "
                                    "see https://www.docker.com/increase-rate-limits/")
                else:
                    logging.error(f"failed to retrieve data for image {image_tag}")
                    traceback.print_exc()
                self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
                self.last_return_value = None
                return self.last_return_value

        if update_available:
            self._set_status(AbstractCheck.CheckResult.POSITIVE)
        else:
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)

        self.last_return_value = update_available
        return self.last_return_value


class CheckIfGitUpdateAvailable(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            return self.last_return_value

        self._report_check()

        cont_config = kwargs.get("cont_config")

        self._update_exec_time()

        if 'gitlab-update-check' in cont_config:
            gitlab = cont_config['gitlab-update-check']
            url = gitlab['url']
            token = gitlab['token']
            project_id = gitlab['project-id']
            dev_branch = gitlab['dev-branch']
            deploy_branch = gitlab['deploy-branch']

            src_update_available = \
                has_diff_between_two_branches(
                    url, token, project_id,
                    dev_branch, deploy_branch)

            if src_update_available:
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
            else:
                self._set_status(AbstractCheck.CheckResult.NEGATIVE)

            self.last_return_value = src_update_available
            return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.NOT_SUPPORTED)

        self.last_return_value = None
        return self.last_return_value


class CheckIfRestarted(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.NEGATIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        name = self.obj_name
        cont = kwargs.get("container")
        prev_inventory = kwargs.get("prev_inventory")
        started_at = dateutil.parser.isoparse(cont.attrs['State']['StartedAt'])

        self._update_exec_time()

        if prev_inventory is not None:
            if name in prev_inventory:
                prev_cont = prev_inventory[name]
                if prev_cont['status'] == 'running':
                    prev_started_at = dateutil.parser.isoparse(prev_cont['started_at'])
                    if prev_started_at != started_at:
                        planned = self.restart_notification_manager.check_notification_present(
                            name, 'container', datetime.datetime.now())
                        severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                        planned = 'as planned' if planned else 'UNPLANNED'

                        self._set_status(AbstractCheck.CheckResult.POSITIVE)

                        logging.warning(f"{name} restarted ({planned})")

                        self._send_smart_alarm(f"container {name} "
                                               f"has been restarted at {started_at} ({planned})",
                                               severity)
                        self.status_acc.fail()
                        self.last_return_value = True
                        return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.NEGATIVE)
        self.last_return_value = False
        return self.last_return_value


class CheckIfContainerStatusChanged(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.NEGATIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        name = self.obj_name
        cur_status = kwargs.get("cur_status")
        prev_inventory = kwargs.get("prev_inventory")

        self._update_exec_time()

        if prev_inventory is not None:
            if name in prev_inventory:
                prev_cont = prev_inventory[name]
                if prev_cont['status'] != cur_status:
                    self._set_status(AbstractCheck.CheckResult.POSITIVE)

                    planned = self.restart_notification_manager.check_notification_present(
                        name, 'container', datetime.datetime.now())
                    severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                    planned = 'as planned' if planned else 'UNPLANNED'

                    logging.warning(f"{name} status changed from {prev_cont['status']} to {cur_status} ({planned})")

                    if cur_status != 'running':
                        self._send_smart_alarm(f"container {name} status "
                                               f"changed from {prev_cont['status']} "
                                               f"to {cur_status} ({planned})",
                                               severity)

                        self.status_acc.fail()
                    self.last_return_value = True
                    return self.last_return_value
                self._set_status(AbstractCheck.CheckResult.NEGATIVE)
                self.last_return_value = False
                return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.NEGATIVE)
        self.last_return_value = False
        return self.last_return_value


class CheckIfContainerStatusIsNotRunning(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.NEGATIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        name = self.obj_name
        cur_status = kwargs.get("cur_status")

        self._update_exec_time()

        if cur_status != 'running':
            self._set_status(AbstractCheck.CheckResult.POSITIVE)

            planned = self.restart_notification_manager.check_notification_present(
                name, 'container', datetime.datetime.now())
            severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
            planned = 'as planned' if planned else 'UNPLANNED'

            logging.warning(f"{name} status is not RUNNING ({cur_status}) ({planned})")

            self._send_smart_alarm(f"container {name} status "
                                   f"is not RUNNING ({cur_status}) ({planned})",
                                   severity)

            self.status_acc.fail()
            self.last_return_value = True
            return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.NEGATIVE)
        self.last_return_value = False
        return self.last_return_value


class CheckIfPortIsOpenInContainerWithNmap(AbstractCheck):
    def __init__(
            self,
            obj_name: str,
            status_acc: OverallStatusAccumulator,
            port,
            alarm_sender: AlarmSender = None,
            restart_notification_manager: RestartNotificationManager = None):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager)
        self.port = port

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        docker_client = kwargs.get('docker_client')

        port = self.port
        container_name = self.obj_name

        self._update_exec_time()

        logs = docker_client.containers.run("networkstatic/nmap",
                                            f"{container_name} -p {port} -sT",
                                            remove=True,
                                            network_mode=f"container:{container_name}")
        logs = logs.decode('utf-8').split("\n")
        pattern = f"{port}/tcp open"
        for line in logs:
            if line.startswith(pattern):
                logging.debug(f"port {port} is open on {container_name}")
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
                self.last_return_value = True
                return self.last_return_value

        logging.debug(f"port {port} is NOT open on {container_name}")
        self._set_status(AbstractCheck.CheckResult.NEGATIVE)

        planned = self.restart_notification_manager.check_notification_present(
            container_name, 'container', datetime.datetime.now())
        severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
        planned = 'as planned' if planned else 'UNPLANNED'
        logging.warning(f"container {container_name}:{port} is DOWN ({planned})")
        self._send_smart_alarm(f"container {container_name} "
                               f"is not responding on port {port} ({planned})",
                               severity)
        self.status_acc.fail()
        self.last_return_value = False
        return self.last_return_value


class CheckIfPortIsOpenInContainer(AbstractCheck):
    def __init__(
            self,
            obj_name: str,
            status_acc: OverallStatusAccumulator,
            port,
            alarm_sender: AlarmSender = None,
            restart_notification_manager: RestartNotificationManager = None):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager)
        self.port = port

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        docker_client = kwargs.get('docker_client')

        port = self.port
        container_name = self.obj_name

        self._update_exec_time()

        try:
            docker_client.containers.run("busybox:latest",
                                         f"nc -zw10 {container_name} {port}",
                                         remove=True,
                                         network_mode=f"container:{container_name}")
            logging.debug(f"port {port} is open on {container_name}")
            self._set_status(AbstractCheck.CheckResult.POSITIVE)
            self.last_return_value = True
            return self.last_return_value
        except docker.errors.ContainerError as err:
            if err.exit_status != 1:
                logging.error(f"unexpected exit status: {str(err)}")

            logging.debug(f"port {port} is NOT open on {container_name}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)

            planned = self.restart_notification_manager.check_notification_present(
                container_name, 'container', datetime.datetime.now())
            severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
            planned = 'as planned' if planned else 'UNPLANNED'
            logging.warning(f"container {container_name}:{port} is DOWN ({planned})")
            self._send_smart_alarm(f"container {container_name} "
                                   f"is not responding on port {port} ({planned})",
                                   severity)
            self.status_acc.fail()
            self.last_return_value = False
            return self.last_return_value
        except docker.errors.DockerException as err:
            logging.error(f"failed to check open port: {str(err)}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = False
            return self.last_return_value


class CheckAllOk(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            return self.last_return_value

        self._report_check()

        all_ok = kwargs.get('all_ok')
        cont_name = self.obj_name

        self._update_exec_time()

        if all_ok:
            self._set_status(AbstractCheck.CheckResult.POSITIVE)
            self.last_return_value = True
            return self.last_return_value

        planned = self.restart_notification_manager.check_notification_present(
            cont_name, 'container', datetime.datetime.now())
        severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
        planned = 'as planned' if planned else 'UNPLANNED'
        logging.warning(f"service {cont_name} is BROKEN ({planned})")
        self._send_smart_alarm(f"container {cont_name} is BROKEN ({planned})",
                               severity)
        self._set_status(AbstractCheck.CheckResult.NEGATIVE)
        self.last_return_value = False
        return self.last_return_value


class DockerChecker(AbstractChecker):
    CHECK_DISK_SPACE = "disk_space"
    CHECK_PORT_OPEN = "port_open"
    CHECK_IMAGE_UPDATE_AVAIL = "image_update_avail"
    CHECK_GIT_UPDATED = "git_updated"
    CHECK_STATUS_CHANGED = "status_changed"
    CHECK_WAS_RESTARTED = "was_restarted"
    CHECK_STATUS_IS_NOT_RUNNING = "status_is_not_running"

    def __init__(self, config, mongo_db, dockers_pool, alarm_sender, restart_notification_manager):
        self.config = config
        self.mongo_db = mongo_db
        self.dockers_pool: DockersPool = dockers_pool
        self.alarm_sender = alarm_sender
        self.restart_notification_manager = restart_notification_manager
        self.stop_flag = False

        self.prev_inventory = None
        self.prev_container_status = {}

        self.last_repo_scan: Optional[datetime.datetime] = None
        self.repo_scan_interval_minutes = 30

        self.checks = {}
        self.status_acc = {}

        for container in self.config['blueprint']:
            cont_name = container['name']
            cont_checks = {}
            status_acc = OverallStatusAccumulator()

            mount_points_thresholds = {}
            for df in container.get('disk-free', []):
                mount_points_thresholds[df['mount']] = float(df['threshold'])

            cont_checks[DockerChecker.CHECK_DISK_SPACE] = CheckFreeDiskSpace(
                cont_name,
                status_acc,
                mount_points_thresholds,
                self.alarm_sender,
                self.restart_notification_manager)
            cont_checks[DockerChecker.CHECK_PORT_OPEN] = {}
            for port in container.get('ports', []):
                cont_checks[DockerChecker.CHECK_PORT_OPEN][port] = CheckIfPortIsOpenInContainer(
                    cont_name,
                    status_acc,
                    port,
                    self.alarm_sender,
                    self.restart_notification_manager)
            cont_checks[DockerChecker.CHECK_IMAGE_UPDATE_AVAIL] = CheckIfImageUpdateIsAvailable(
                cont_name,
                status_acc,
                self.alarm_sender,
                self.restart_notification_manager,
                600)
            cont_checks[DockerChecker.CHECK_GIT_UPDATED] = CheckIfGitUpdateAvailable(
                cont_name,
                status_acc,
                self.alarm_sender,
                self.restart_notification_manager,
                600)
            cont_checks[DockerChecker.CHECK_STATUS_CHANGED] = CheckIfContainerStatusChanged(
                cont_name,
                status_acc,
                self.alarm_sender,
                self.restart_notification_manager)
            cont_checks[DockerChecker.CHECK_WAS_RESTARTED] = CheckIfRestarted(
                cont_name,
                status_acc,
                self.alarm_sender,
                self.restart_notification_manager)
            cont_checks[DockerChecker.CHECK_STATUS_IS_NOT_RUNNING] = CheckIfContainerStatusIsNotRunning(
                cont_name,
                status_acc,
                self.alarm_sender,
                self.restart_notification_manager)

            self.checks[cont_name] = cont_checks
            self.status_acc[cont_name] = status_acc

        for container in self.config['blueprint']:
            cont_name = container['name']
            self.prev_container_status[cont_name] = {'status': 'OK'}
            if container.get('friendly-name', None):
                self.prev_container_status[cont_name]['friendly-name'] \
                    = container['friendly-name']
            if container.get('desc', None):
                self.prev_container_status[cont_name]['desc'] \
                    = container['desc']
            if container.get('panel', None):
                self.prev_container_status[cont_name]['panel'] \
                    = container['panel']
            if container.get('src', None):
                self.prev_container_status[cont_name]['src'] \
                    = container['src']

        mongo_db['container_status'].create_index([('timestamp', -1)])

        last_status = self.mongo_db['container_status'].find_one(sort=[('timestamp', -1)])
        if last_status:
            for obj_name in last_status.get('status', {}):
                if obj_name in self.prev_container_status:
                    if 'status' in last_status['status'][obj_name]:
                        self.prev_container_status[obj_name]['status'] = last_status['status'][obj_name]['status']
                    if 'stats' in last_status['status'][obj_name]:
                        self.prev_container_status[obj_name]['stats'] = last_status['status'][obj_name]['stats']

    def request_stop(self):
        self.stop_flag = True

    def check(self):
        logging.debug("starting verification procedure")

        inventory = {}

        for template in self.config['blueprint']:
            if self.stop_flag:
                return

            cont_name = template['name']
            logging.debug(f"checking {cont_name}")

            checks = self.checks[cont_name]

            docker_client = self.get_docker_client_for_container(template)

            if docker_client is None:
                logging.warning(f"docker client not yet available for {template['name']}")
                continue

            try:
                cont = docker_client.containers.get(cont_name)
            except docker.errors.NotFound:
                logging.error(f"container {template['name']} not found")
                continue
            except docker.errors.APIError as e:
                logging.error(f"error retrieving container {template['name']}"+str(e))
                continue

            logging.debug(f"loading data for container {cont.name}")

            update_available: Optional[bool] = \
                    checks[DockerChecker.CHECK_IMAGE_UPDATE_AVAIL].do_check(container=cont, cont_config=template)

            src_update_available: Optional[bool] = \
                    checks[DockerChecker.CHECK_GIT_UPDATED].do_check(cont_config=template)

            stats = self._compute_stats(docker_client, cont, checks)
            cont_rec = {
                'name': cont.name,
                'short_id': cont.short_id,
                'status': cont.status,  # running
                'created': cont.attrs['Created'],
                'state': cont.attrs['State'],
                'started_at': cont.attrs['State']['StartedAt'],
                'restart_count': cont.attrs['RestartCount'],
                'env': cont.attrs['Config']['Env'],
                'networks': cont.attrs['NetworkSettings']['Networks'],  # .preprod.Aliases[0]
                'stats': stats,
                'update_available': update_available,
                'src_update_available': src_update_available
            }

            inventory[cont.name] = cont_rec

            status_acc = self.status_acc[cont_name]
            status_acc.reset_status()

            checks[DockerChecker.CHECK_STATUS_IS_NOT_RUNNING].do_check(
                cur_status=cont_rec['status'])

            checks[DockerChecker.CHECK_STATUS_CHANGED].do_check(
                cur_status=cont_rec['status'],
                prev_inventory=self.prev_inventory
            )

            checks[DockerChecker.CHECK_WAS_RESTARTED].do_check(
                container=cont,
                prev_inventory=self.prev_inventory
            )

            for port in template.get('ports', []):
                checks[DockerChecker.CHECK_PORT_OPEN][port].do_check(docker_client=docker_client)

            if status_acc.is_ok():
                logging.debug('all OK')

            container_status = 'OK' if status_acc.is_ok() else 'NOK'

            if cont_name not in self.prev_container_status:
                self.prev_container_status[cont_name] = {'status': container_status}

            prev_container_status = self.prev_container_status[cont_name]

            if cont_name in self.prev_container_status and \
                    container_status != prev_container_status['status']:
                if container_status == 'OK':
                    logging.info(f"container {cont_name} has been repaired")
                    self.alarm_sender.push_alarm(f"container {cont_name} is OK again", AlarmSeverity.INFO)
                else:
                    planned = self.restart_notification_manager.check_notification_present(
                        cont_name, 'container', datetime.datetime.now())
                    severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                    planned = 'as planned' if planned else 'UNPLANNED'
                    logging.warning(f"service {cont_name} is BROKEN ({planned})")
                    self.alarm_sender.push_alarm(f"container {cont_name} is BROKEN ({planned})",
                                                 severity)

            prev_container_status['status'] = container_status
            if container_status != 'OK':
                prev_container_status['last_failure'] \
                    = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if cont_rec:
                prev_container_status['stats'] = cont_rec['stats']
                if cont_rec['update_available'] is not None:
                    prev_container_status['update_available']: bool = cont_rec['update_available']
                elif self.prev_container_status[cont_name].get('update_available', None) is None:
                    prev_container_status['update_available']: bool = False
                if cont_rec['src_update_available'] is not None:
                    prev_container_status['src_update_available'] = cont_rec['src_update_available']

        self.prev_inventory = inventory

    @staticmethod
    def _compute_stats(docker_client, cont, checks):
        checker: AbstractCheck = checks[DockerChecker.CHECK_DISK_SPACE]  # TODO: use one check per mount point
        df_root = checker.do_check(docker_client=docker_client, local_source='/')

        now = datetime.datetime.now(datetime.timezone.utc)
        started_at = dateutil.parser.isoparse(cont.attrs['State']['StartedAt'])
        uptime = now - started_at

        ins = docker_client.api.inspect_container(cont.name)
        df = {df_root['mount_point']: df_root} if df_root else {}
        mounts = ins['Mounts']
        for mount in mounts:
            source = mount.get('Source', None)
            if source:
                df_mount = checker.do_check(docker_client=docker_client, local_source=source)
                if df_mount and not df_mount['mount_point'] in df:
                    df[df_mount['mount_point']] = df_mount

        st = cont.stats(stream=False)
        network_if = None
        if 'networks' in st:
            network_if = list(st['networks'].items())[0][1]
        blkio_stat = st['blkio_stats']['io_service_bytes_recursive']
        bytes_written = 0
        bytes_read = 0
        if blkio_stat is not None:
            for x in blkio_stat:
                op = x.get('op', '').lower()
                if op == 'write':
                    bytes_written += x['value']
                elif op == 'read':
                    bytes_read += x['value']
        cpu_delta = st['cpu_stats']['cpu_usage'].get('total_usage', 0) - \
                    st['precpu_stats']['cpu_usage']['total_usage']
        system_cpu_delta = st['cpu_stats'].get('system_cpu_usage', 0) - st['precpu_stats'].get('system_cpu_usage', 0)
        number_cpus = st['cpu_stats']['online_cpus']
        cpu_usage = (cpu_delta / system_cpu_delta) * number_cpus

        used_memory_bytes = st['memory_stats']['usage'] - st['memory_stats']['stats'].get('cache', 0)
        available_memory_bytes = st['memory_stats']['limit']
        memory_usage = used_memory_bytes / available_memory_bytes

        return {
            'cpu_usage_percent': 100.0 * cpu_usage,
            'memory_usage_bytes': used_memory_bytes,
            'memory_available_bytes': available_memory_bytes,
            'memory_usage_percent': 100.0 * memory_usage,
            'pids': st['pids_stats']['current'],
            'network_received_bytes': network_if['rx_bytes'] if network_if else None,
            'network_sent_bytes': network_if['tx_bytes'] if network_if else None,
            'blkio_written_bytes': bytes_written,
            'blkio_read_bytes': bytes_read,
            'uptime_seconds': uptime.total_seconds(),
            'disk_usage': list(df.values())
        }

    def store_status(self):
        if self.mongo_db is None:
            return

        rec = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            'status': self.prev_container_status,
        }

        self.mongo_db['container_status'].insert_one(rec)

    def get_status(self):
        return self.prev_container_status

    def get_stats_for_container(self, container, stat, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['container_status'].find({'timestamp': {'$gt': time_from} }, {
            '_id': 0, 'timestamp': 1, f'status.{container}.stats.{stat}': 1},
                                            sort=[('timestamp', 1)]))

    def get_status_timeseries_for_container(self, container, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['container_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{container}.status': 1},
                                            sort=[('timestamp', 1)]))

    def get_status_timeseries(self, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['container_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, 'status.$': 1},
                                            sort=[('timestamp', 1)]))

    def get_docker_client_for_container(self, cont_config):
        docker_id = cont_config.get('docker', None)

        if docker_id is None:
            return self.dockers_pool.get_default_client()

        if self.dockers_pool.has_client_with_id(docker_id):
            # client can be None if it could not be loaded yet
            return self.dockers_pool.get_client_for_id(docker_id)

        raise ValueError(f"docker id {docker_id} is not defined")
