import datetime
import logging
import os
import re
import shlex
import socket
import struct
from typing import List, Union, Optional
import urllib
import ssl
import OpenSSL

import docker.errors
import requests
from requests.auth import HTTPBasicAuth

from alarms.alarm import AlarmSeverity
from alarms.alarm import AlarmSender
from checkers.abstract_checker import AbstractChecker
from checkers.check import AbstractCheck, OverallStatusAccumulator
from checkers.docker_checker import CheckIfGitUpdateAvailable
from utils.dockers_pool import DockersPool
from utils.restart_notification_manager import RestartNotificationManager


class CurlAuth:
    def get_curl_params(self):
        raise NotImplementedError()


class CurlBasicAuth(CurlAuth):
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def get_curl_params(self):
        return f"-u {self.username}:{self.password}"


class CheckZabbix(AbstractCheck):
    def do_check(self, **kwargs):
        if not self.shall_repeat():
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        checks: dict[str: Union[dict[str: AbstractCheck] | AbstractCheck]] = kwargs.get("checks")
        hostname: str = kwargs.get("hostname")
        zab_desc: dict = kwargs.get("zab_desc")

        mount_points_thresholds = {}
        for df in zab_desc.get('disk-free', []):
            mount_points_thresholds[df['mount']] = float(df['threshold'])
        for df in zab_desc.get('mount-points', []):
            if df not in mount_points_thresholds:
                mount_points_thresholds[df] = None
        nic_list: List[str] = zab_desc.get('nic', [])
        ports: List[str] = zab_desc.get('ports', [])
        mount_points = list(mount_points_thresholds.keys())

        ports = [str(x) for x in ports]
        ports = [x.replace(':', ',') for x in ports]
        ports = [',' + x if ',' not in x else x for x in ports]

        zab_stats = CheckZabbix._get_zabbix_stats_internal(hostname,
                                                           mount_points=mount_points,
                                                           nic_list=nic_list,
                                                           port_list=ports)

        for port in ports:
            checks[WebServiceChecker.CHECK_PORT_OPEN_ZABBIX][port].do_check(zab_stats=zab_stats)

        disk_stat = []
        for mount_point in mount_points:
            disk_total = zab_stats['vfs.fs.size[' + mount_point + ',total]']
            disk_free = zab_stats['vfs.fs.size[' + mount_point + ',free]']
            if disk_total is not None and disk_free is not None:
                disk_used = disk_total - disk_free
                disk_usage_perc = 100.0 * disk_used / disk_total
                disk_stat.append({
                    'mount_point': mount_point,
                    'total_bytes': disk_total,
                    'used_bytes': disk_used,
                    'usage_percentage': disk_usage_perc
                })
                checks[WebServiceChecker.CHECK_DISK_SPACE_IS_OK_ZABBIX][mount_point].\
                    do_check(disk_usage_perc=disk_usage_perc)

        network_sent_bytes = 0
        network_rcvd_bytes = 0
        for nic in nic_list:
            bytes_in = zab_stats[f'net.if.in[{nic},bytes]']
            bytes_out = zab_stats[f'net.if.out[{nic},bytes]']
            network_rcvd_bytes += bytes_in if bytes_in else 0
            network_sent_bytes += bytes_out if bytes_out else 0

        mem_usage_percent = 100.0 * zab_stats['vm.memory.size[free]'] / zab_stats['vm.memory.size'] \
            if zab_stats['vm.memory.size[free]'] is not None and zab_stats['vm.memory.size'] \
            else 0

        self.last_return_value = {
            'cpu_usage_percent': zab_stats['system.cpu.load'],
            'memory_usage_bytes': zab_stats['vm.memory.size'],
            'memory_available_bytes': zab_stats['vm.memory.size[free]'],
            'memory_usage_percent': mem_usage_percent,
            'pids': zab_stats['proc.num'],
            'network_received_bytes': network_rcvd_bytes,
            'network_sent_bytes': network_sent_bytes,
            'blkio_written_bytes': zab_stats['vfs.dev.write[all,sectors]'],
            'blkio_read_bytes': zab_stats['vfs.dev.read[all,sectors]'],
            'uptime_seconds': zab_stats['system.uptime'],
            'disk_usage': disk_stat
        }

        return self.last_return_value

    @staticmethod
    def _get_zabbix_stats_internal(zabbix_host, zabbix_port=10050, mount_points=None, nic_list=None, port_list=None):
        params = ["vm.memory.size", "vm.memory.size[free]", "proc.num",
                  "system.cpu.load", "system.cpu.util",
                  "system.uptime",
                  "net.if.in[enp3s0,bytes]", "net.if.out[enp3s0,bytes]",
                  "vfs.dev.read[all,sectors]", "vfs.dev.write[all,sectors]"]

        if mount_points:
            for mp in mount_points:
                params.append(f"vfs.fs.size[{mp},total]")
                params.append(f"vfs.fs.size[{mp},free]")

        if port_list:
            for port in port_list:
                params.append(f"net.tcp.port[{port}]")

        if nic_list:
            for nic in nic_list:
                params.append(f"net.if.in[{nic},bytes]")
                params.append(f"net.if.out[{nic},bytes]")

        ret = {}

        for p in params:
            str_val = CheckZabbix._get_zabbix_param(p, zabbix_host, zabbix_port)
            if str_val is None:
                ret[p] = None
            else:
                try:
                    ret[p] = int(str_val)
                except ValueError:
                    try:
                        ret[p] = float(str_val)
                    except ValueError:
                        if str_val.startswith('ZBX_NOTSUPPORTED'):
                            err_text = str_val.split('\x00')[1]
                            logging.error(f"zabbix error: {err_text}")
                        ret[p] = None

        return ret

    @staticmethod
    def _get_zabbix_param(param, zabbix_host, zabbix_port=10050):
        try:
            client_socket = socket.socket()
            client_socket.connect((zabbix_host, zabbix_port))

            request = (param + "\n").encode()
            packet = b"ZBXD\1" + struct.pack("<Q", len(request)) + request

            client_socket.send(packet)
            data = client_socket.recv(1024)
            hdr = data[0:5]
            if hdr != b"ZBXD\1":
                logging.warning(f"incorrect header {hdr}")
                return None
            # rlenp = data[5:5+8]
            # rlen = struct.unpack("<Q", rlenp)[0]
            # print(f"hdr={hdr} len={rlen}")
            content = data[5+8:].decode()

            logging.debug(f'{param}={content}')
            client_socket.close()

            return content
        except OSError as error:
            logging.error(f"failed to connect to zabbix at {zabbix_host}: {str(error)}")

            return None


class CheckServicePortOpenZabbix(AbstractCheck):

    def __init__(self, obj_name: str, status_acc: OverallStatusAccumulator,
                 hostname: str, port: Union[str, int], alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.hostname = hostname
        self.port = port

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        zab_stats = kwargs.get('zab_stats')
        port_status = zab_stats.get(f"net.tcp.port[{self.port}]", None)
        if port_status != 1:
            planned = self.restart_notification_manager.check_notification_present(
                self.obj_name, 'service', datetime.datetime.now())
            severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
            planned = 'as planned' if planned else 'UNPLANNED'

            logging.warning(f"service {self.obj_name} port {self.port} (zabbix check) is DOWN ({planned})")
            self._send_smart_alarm(f"service {self.obj_name} "
                                   f"zabbix check: port {self.port} is not open ({planned})",
                                   severity)
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = None
            self.status_acc.fail()
            return self.last_return_value
        if port_status is None:
            logging.warning(f"service {self.obj_name}:{self.port} is not monitored by zabbix")
            self.status_acc.fail()
            self.last_return_value = False
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            return self.last_return_value

        self._set_status(AbstractCheck.CheckResult.POSITIVE)
        self.last_return_value = True
        return self.last_return_value


class CheckDiskSpaceIsOkZabbix(AbstractCheck):

    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 mount_point: str,
                 threshold: float = None,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.mount_point = mount_point
        default_disk_usage_threshold = float(os.getenv("DEFAULT_DISK_USAGE_THRESHOLD", "80"))
        self.threshold = threshold if threshold is not None else default_disk_usage_threshold

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        disk_usage_perc = kwargs.get('disk_usage_perc')

        if disk_usage_perc is not None and self.is_disk_usage_too_high(disk_usage_perc):
            logging.warning(f"service {self.obj_name} disk {self.mount_point} "
                            f"usage is too high ({disk_usage_perc:.2f}%)")

            self._set_status(AbstractCheck.CheckResult.NEGATIVE)

            self._send_smart_alarm(
                f"container {self.obj_name} disk {self.mount_point} "
                f"usage is too high ({disk_usage_perc:.2f}%)",
                AlarmSeverity.ALARM)

            self.status_acc.fail()
            self.last_return_value = False
        else:
            self._set_status(AbstractCheck.CheckResult.POSITIVE)

            self.last_return_value = True
            self.status_acc.fail()

        return self.last_return_value

    def is_disk_usage_too_high(self, usage_percentage):
        if usage_percentage > self.threshold:
            return True

        return False


class CheckServicePortOpenWithNmap(AbstractCheck):

    def __init__(self, obj_name: str, status_acc: OverallStatusAccumulator,
                 hostname: str, port: Union[str, int], alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.hostname = hostname
        self.port = port

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        docker_client = kwargs.get('docker_client')
        if docker_client is None:
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.last_return_value = None
            self.status_acc.fail()
            return self.last_return_value

        port = self.port
        hostname = self.hostname

        try:
            logs = docker_client.containers.run("networkstatic/nmap",
                                                f"{hostname} -p {port} -sT",
                                                remove=True)
            logs = logs.decode('utf-8').split("\n")
            pattern = f"{port}/tcp open"
            for line in logs:
                if line.startswith(pattern):
                    logging.debug(f"port {port} is open on {hostname}")
                    self._set_status(AbstractCheck.CheckResult.POSITIVE)
                    self.last_return_value = True
                    return self.last_return_value
            logging.debug(f"port {port} is NOT open on {hostname}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            planned = self.restart_notification_manager.check_notification_present(
                self.obj_name, 'service', datetime.datetime.now())
            severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
            planned = 'as planned' if planned else 'UNPLANNED'

            logging.warning(f"service {self.obj_name}:{port} is DOWN ({planned})")
            self._send_smart_alarm(f"server {self.obj_name} is "
                                   f"not responding on port {port} ({planned})",
                                   severity)
            self.status_acc.fail()
            self.last_return_value = False
            return self.last_return_value
        except docker.errors.DockerException as e:
            logging.error(f"failed to run port checking container: {e}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value


class CheckServicePortOpen(AbstractCheck):

    def __init__(self, obj_name: str, status_acc: OverallStatusAccumulator,
                 hostname: str, port: Union[str, int], alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.hostname = hostname
        self.port = port

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        docker_client = kwargs.get('docker_client')
        if docker_client is None:
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.last_return_value = None
            self.status_acc.fail()
            return self.last_return_value

        port = self.port
        hostname = self.hostname

        try:
            docker_client.containers.run("busybox:latest",
                                         f"nc -zw10 {hostname} {port}",
                                         remove=True)
            logging.debug(f"port {port} is open on {hostname}")
            self._set_status(AbstractCheck.CheckResult.POSITIVE)
            self.last_return_value = True
            return self.last_return_value
        except docker.errors.ContainerError as err:
            if err.exit_status != 1:
                logging.error(f"unexpected exit status: {str(err)}")
            logging.debug(f"port {port} is NOT open on {hostname}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            planned = self.restart_notification_manager.check_notification_present(
                self.obj_name, 'service', datetime.datetime.now())
            severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
            planned = 'as planned' if planned else 'UNPLANNED'

            logging.warning(f"service {self.obj_name}:{port} is DOWN ({planned})")
            self._send_smart_alarm(f"server {self.obj_name} is "
                                   f"not responding on port {port} ({planned})",
                                   severity)
            self.status_acc.fail()
            self.last_return_value = False
            return self.last_return_value
        except docker.errors.DockerException as e:
            logging.error(f"failed to run port checking container: {e}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value


class CheckServiceEndpointAvailable(AbstractCheck):

    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 endpoint: dict,
                 exp_code: List[int] = None,
                 method: str = "GET",
                 push_data: str = None,
                 auth: Optional[CurlAuth] = None,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.endpoint = endpoint
        self.exp_code = exp_code if exp_code is not None else [200, 201, 204]
        self.method = method
        self.push_data = push_data
        self.auth = auth

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        docker_client = kwargs.get('docker_client')
        if docker_client is None:
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.last_return_value = None
            self.status_acc.fail()
            return self.last_return_value

        url = self.endpoint['url']
        auth_curl_param = self.auth.get_curl_params() if self.auth else ''
        push_data = ''
        extra_curl_params = self.endpoint.get('extra_curl_params', '')
        extra_headers = self.endpoint.get('extra_headers', {})
        extra_headers_str = ''
        for eh_name, eh_value in extra_headers.items():
            if extra_headers_str != '':
                extra_headers_str += ' '
            extra_headers_str += f'-H "{eh_name}: {eh_value}"'
        if self.push_data:
            push_data = f'-d {shlex.quote(self.push_data)}'
        try:
            logs = docker_client.containers.run("curlimages/curl",
                                                f"-v -s -L -X {self.method} {extra_headers_str} {push_data} {auth_curl_param} {extra_curl_params} {url}",
                                                remove=True, stdout=True, stderr=True)
            logs = logs.decode('utf-8').split("\n")
            pattern = re.compile(r'^< HTTP/[0-9.]+\s+(\d+)\s+.*$')
            http_code = None
            # in case of 30x redirect, first the 30x code will be printed
            # to get the actual HTTP response code we need to parse the whole output and get the last one
            for line in logs:
                m = pattern.match(line)
                if m:
                    http_code = int(m.group(1))
                    break

            if http_code and http_code in self.exp_code:
                logging.debug(f"endpoint {url} is ok")
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
                self.last_return_value = True
                return self.last_return_value
            logging.debug(f"endpoint {url} responded with unexpected HTTP code {http_code}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = False
            self.status_acc.fail()
            return self.last_return_value
        except docker.errors.ContainerError as err:  # non-zero exist status = failure
            logging.error(f"error - non-zero curl exit status: {err}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = False
            self.status_acc.fail()
            return self.last_return_value
        except docker.errors.DockerException as err:
            logging.error(f"error when running curl in container: {err}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.last_return_value = None
            self.status_acc.fail()
            return self.last_return_value


class CheckServiceEndpointAvailableDirect(AbstractCheck):

    def __init__(self,
                 obj_name: str,
                 status_acc: OverallStatusAccumulator,
                 endpoint: dict,
                 exp_code: List[int] = None,
                 method: str = "GET",
                 push_data: str = None,
                 auth: Optional[CurlAuth] = None,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.endpoint = endpoint
        self.exp_code = exp_code if exp_code is not None else [200, 201, 204]
        self.method = method
        self.push_data = push_data
        self.auth = auth

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        url = self.endpoint['url']

        extra_headers = self.endpoint.get('extra_headers', {})

        auth = None
        if self.auth and isinstance(self.auth, CurlBasicAuth):
            auth = HTTPBasicAuth(self.auth.username, self.auth.password)
        try:
            resp = requests.request(url=url, method=self.method, auth=auth, headers=extra_headers, timeout=120, data=self.push_data)
            if resp.status_code in self.exp_code:
                logging.debug(f"endpoint {url} is ok")
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
                self.last_return_value = True
                return self.last_return_value
            logging.debug(f"endpoint {url} responded with unexpected HTTP code {resp.status_code} {resp}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = False
            self.status_acc.fail()
            return self.last_return_value
        except (ConnectionError, requests.exceptions.RequestException) as err:
            logging.error(f"error requesting {url}: {err}")
            self._set_status(AbstractCheck.CheckResult.NEGATIVE)
            self.last_return_value = False
            self.status_acc.fail()
            return self.last_return_value


class CheckSslCertNotExpired(AbstractCheck):

    def __init__(self, obj_name: str, status_acc: OverallStatusAccumulator,
                 url: str,
                 old_certif_days_to_warn: int,
                 alarm_sender: AlarmSender = None,
                 restart_notification_manager: RestartNotificationManager = None,
                 check_repeat_interval: int = AbstractCheck.DEFAULT_CHECK_REPEAT_INTERVAL,
                 resend_threshold: int = AbstractCheck.DEFAULT_RESEND_THRESHOLD):
        super().__init__(obj_name, status_acc, alarm_sender, restart_notification_manager, check_repeat_interval,
                         resend_threshold)
        self.url = url
        self.old_certif_days_to_warn = old_certif_days_to_warn

    def do_check(self, **kwargs):
        if not self.shall_repeat():
            if self.get_last_status() != AbstractCheck.CheckResult.POSITIVE:
                self.status_acc.fail()
            return self.last_return_value

        self._report_check()

        self._update_exec_time()

        try:
            src = urllib.parse.urlparse(self.url)
            if src.scheme != "https":
                self._set_status(AbstractCheck.CheckResult.POSITIVE)
                self.last_return_value = True
                return self.last_return_value
            port = src.port if src.port is not None else 443
            certificate = ssl.get_server_certificate((src.hostname, port))
            x509_cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, certificate)
            not_after_str = x509_cert.get_notAfter().decode("utf-8")
            not_after = datetime.datetime.strptime(not_after_str, '%Y%m%d%H%M%S%z').date()
            expires_in = not_after - datetime.datetime.now().date()
            if expires_in < datetime.timedelta(days=self.old_certif_days_to_warn):
                logging.warning(f"certificate on {self.url} is expiring in {expires_in}")
                self._set_status(AbstractCheck.CheckResult.NEGATIVE)
                self.last_return_value = False
                self.status_acc.fail()
                planned = self.restart_notification_manager.check_notification_present(
                    self.obj_name, 'service', datetime.datetime.now())
                severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                planned = 'as planned' if planned else 'UNPLANNED'

                logging.warning(f"service {self.obj_name} endpoint {self.url} is DOWN ({planned})")
                self._send_smart_alarm(f"service {self.obj_name} "
                                       f"endpoint {self.url} is not functioning ({planned})",
                                       severity)
                return self.last_return_value
            self._set_status(AbstractCheck.CheckResult.POSITIVE)
            self.last_return_value = True
            return self.last_return_value
        except ConnectionError as err:
            logging.error(f"failed to retrieve certificate from {self.url}: {str(err)}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value
        except socket.gaierror as err:
            logging.error(f"failed to retrieve certificate from {self.url}: {str(err)}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value
        except ssl.SSLError as err:
            logging.error(f"failed to retrieve certificate from {self.url}: {str(err)}")
            self._set_status(AbstractCheck.CheckResult.EXEC_FAILURE)
            self.status_acc.fail()
            self.last_return_value = None
            return self.last_return_value


class WebServiceChecker(AbstractChecker):
    CHECK_SSL_CERT_EXPIRATION = "check_ssl_cert_expiration"
    CHECK_PORT_OPEN = "check_port_open"
    CHECK_PORT_OPEN_ZABBIX = "check_port_open_zabbix"
    CHECK_DISK_SPACE_IS_OK_ZABBIX = "check_disk_space_is_ok_zabbix"
    CHECK_ENDPOINT_AVAIL = "check_endpoint_avail"
    CHECK_GIT_UPDATED = "git_updated"
    CHECK_ZABBIX = "check_zabbix"

    def __init__(self, config, mongo_db, dockers_pool: DockersPool,
                 alarm_sender: AlarmSender, restart_notification_manager):
        self.config = config
        self.mongo_db = mongo_db
        self.dockers_pool = dockers_pool

        self.alarm_sender = alarm_sender
        self.restart_notification_manager = restart_notification_manager

        self.prev_service_status = {}
        self.stop_flag = False

        self.old_certif_days_to_warn = int(os.getenv('EXPIRING_CERTIFICATE_WARN_DAYS', '30'))

        self.checks = {}
        self.status_acc = {}

        for service in self.config['services']:
            service_name = service['name']

            serv_checks = {}
            status_acc = OverallStatusAccumulator()
            self.status_acc[service_name] = status_acc
            self.checks[service_name] = serv_checks

            serv_checks[WebServiceChecker.CHECK_ZABBIX] = \
                CheckZabbix(
                    service_name,
                    status_acc,
                    self.alarm_sender,
                    self.restart_notification_manager)

            serv_checks[WebServiceChecker.CHECK_GIT_UPDATED] = \
                CheckIfGitUpdateAvailable(
                    service_name,
                    status_acc,
                    self.alarm_sender,
                    self.restart_notification_manager,
                    600)  # run every 10 minutes

            serv_checks[WebServiceChecker.CHECK_PORT_OPEN] = {}
            for port in service.get('ports', []):
                serv_checks[WebServiceChecker.CHECK_PORT_OPEN][port] = \
                    CheckServicePortOpen(
                        service_name,
                        status_acc,
                        service['hostname'],
                        port,
                        self.alarm_sender,
                        self.restart_notification_manager)

            zabbix_cfg = service.get('zabbix', {})
            serv_checks[WebServiceChecker.CHECK_PORT_OPEN_ZABBIX] = {}
            # old notation, without free disk threshold
            mount_points: List[str] = zabbix_cfg.get('mount-points', [])
            # new notation, with free disk threshold
            disk_free: List[str] = zabbix_cfg.get('disk-free', [])
            mount_points_thresholds = {}
            for df in disk_free:
                mount_points_thresholds[df['mount']] = float(df['threshold'])
            for df in mount_points:
                if df not in mount_points_thresholds:
                    mount_points_thresholds[df] = None
            serv_checks[WebServiceChecker.CHECK_DISK_SPACE_IS_OK_ZABBIX] = {}
            for (df, thrsld) in mount_points_thresholds.items():
                serv_checks[WebServiceChecker.CHECK_DISK_SPACE_IS_OK_ZABBIX][df] = \
                    CheckDiskSpaceIsOkZabbix(
                        service_name,
                        status_acc,
                        df,
                        thrsld,
                        self.alarm_sender,
                        self.restart_notification_manager)

            for zab_port in zabbix_cfg.get('ports', []):
                zab_port = str(zab_port).replace(':', ',')
                zab_port = ',' + zab_port if ',' not in zab_port else zab_port
                serv_checks[WebServiceChecker.CHECK_PORT_OPEN_ZABBIX][zab_port] = \
                    CheckServicePortOpenZabbix(
                        service_name,
                        status_acc,
                        service['hostname'],
                        zab_port,
                        self.alarm_sender,
                        self.restart_notification_manager)
            serv_checks[WebServiceChecker.CHECK_ENDPOINT_AVAIL] = {}
            serv_checks[WebServiceChecker.CHECK_SSL_CERT_EXPIRATION] = {}
            for endpoint in service.get('endpoints', []):
                auth = None
                if 'auth' in endpoint:
                    auth_type = next(iter(endpoint['auth'].keys()))
                    if auth_type == 'basic':
                        username = endpoint['auth']['basic']['username']
                        password = endpoint['auth']['basic']['password']
                        auth = CurlBasicAuth(username, password)
                method = endpoint.get('method', 'GET')
                push_data = endpoint.get('data', None)
                direct = endpoint.get('type', 'docker') == 'direct'
                exp_code = endpoint.get('exp_code', (200, 201, 204))
                serv_checks[WebServiceChecker.CHECK_ENDPOINT_AVAIL][endpoint['url']] = \
                    CheckServiceEndpointAvailableDirect(
                        service_name,
                        status_acc,
                        endpoint,
                        exp_code,
                        method,
                        push_data,
                        auth,
                        self.alarm_sender,
                        self.restart_notification_manager
                    ) if direct else \
                        CheckServiceEndpointAvailable(
                            service_name,
                            status_acc,
                            endpoint,
                            exp_code,
                            method,
                            push_data,
                            auth,
                            self.alarm_sender,
                            self.restart_notification_manager)
                serv_checks[WebServiceChecker.CHECK_SSL_CERT_EXPIRATION][endpoint['url']] = \
                    CheckSslCertNotExpired(
                        service_name,
                        status_acc,
                        endpoint['url'],
                        self.old_certif_days_to_warn,
                        self.alarm_sender,
                        self.restart_notification_manager,
                        3600  # run one per hour
                    )

            self.prev_service_status[service_name] = {'status': 'OK'}
            if service.get('friendly-name', None):
                self.prev_service_status[service_name]['friendly-name'] \
                    = service['friendly-name']
            if service.get('desc', None):
                self.prev_service_status[service_name]['desc'] \
                    = service['desc']
            if service.get('panel', None):
                self.prev_service_status[service_name]['panel'] \
                    = service['panel']
            if service.get('src', None):
                self.prev_service_status[service_name]['src'] \
                    = service['src']

        mongo_db['service_status'].create_index([('timestamp', -1)])

        last_status = mongo_db['service_status'].find_one(sort=[('timestamp', -1)])
        if last_status:
            for obj_name in last_status.get('status', {}):
                if obj_name in self.prev_service_status:
                    if 'status' in last_status['status'][obj_name]:
                        self.prev_service_status[obj_name]['status'] = last_status['status'][obj_name]['status']

    def request_stop(self):
        self.stop_flag = True

    def check(self):
        for service in self.config['services']:
            if self.stop_flag:
                return
            logging.debug(f"checking service {service['name']}")

            serv_name = service['name']

            checks = self.checks[serv_name]
            status_acc = self.status_acc[serv_name]
            status_acc.reset_status()

            docker_client = self._get_docker_client_for_service(service)
            if docker_client is None:
                logging.warning(f"docker client not yet available for {service['name']}")

            src_update_available: Optional[bool] = \
                    checks[WebServiceChecker.CHECK_GIT_UPDATED].do_check(cont_config=service)

            stats = {}

            if 'zabbix' in service:
                stats = checks[WebServiceChecker.CHECK_ZABBIX].do_check(
                    checks=checks,
                    hostname=service['hostname'],
                    zab_desc=service['zabbix'])

            for port in service.get('ports', []):
                checks[WebServiceChecker.CHECK_PORT_OPEN][port].do_check(docker_client=docker_client)

            for endpoint in service.get('endpoints', []):
                checks[WebServiceChecker.CHECK_ENDPOINT_AVAIL][endpoint['url']].do_check(docker_client=docker_client)

                checks[WebServiceChecker.CHECK_SSL_CERT_EXPIRATION][endpoint['url']].do_check()

            if status_acc.is_ok():
                logging.debug('all OK')

            service_status = 'OK' if status_acc.is_ok() else 'NOK'

            if serv_name not in self.prev_service_status:
                self.prev_service_status[serv_name] = {'status': service_status}

            if serv_name in self.prev_service_status and \
                    service_status != self.prev_service_status[serv_name]['status']:
                if service_status == 'OK':
                    logging.info(f"service {serv_name} has been repaired")
                    self.alarm_sender.push_alarm(f"service {service['name']} is OK again", AlarmSeverity.INFO)
                else:
                    planned = self.restart_notification_manager.check_notification_present(
                        serv_name, 'service', datetime.datetime.now())
                    severity = AlarmSeverity.INFO if planned else AlarmSeverity.ALARM
                    planned = 'as planned' if planned else 'UNPLANNED'

                    logging.warning(f"service {serv_name} is BROKEN ({planned})")
                    self.alarm_sender.push_alarm(f"service {serv_name} is BROKEN ({planned})", severity)

            self.prev_service_status[serv_name]['status'] = service_status
            if service_status != 'OK':
                self.prev_service_status[serv_name]['last_failure'] \
                    = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.prev_service_status[serv_name]['stats'] = stats
            self.prev_service_status[serv_name]['src_update_available'] = src_update_available

    def store_status(self):
        if self.mongo_db is None:
            return

        rec = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            'status': self.prev_service_status
        }

        self.mongo_db['service_status'].insert_one(rec)

    def get_status(self):
        return self.prev_service_status

    def get_status_timeseries_for_service(self, service, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['service_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{service}.status': 1},
                                            sort=[('timestamp', 1)]))

    def get_stats_for_service(self, service, stat, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['service_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, f'status.{service}.stats.{stat}': 1},
                                            sort=[('timestamp', 1)]))

    def get_status_timeseries(self, time_from=None):
        if time_from is None:
            time_from = datetime.datetime.now() - datetime.timedelta(days=1)

        return list(self.mongo_db['service_status'].find({'timestamp': {'$gt': time_from}}, {
            '_id': 0, 'timestamp': 1, 'status.$': 1},
                                            sort=[('timestamp', 1)]))

    def _get_docker_client_for_service(self, cont_config):
        docker_id = cont_config.get('docker', None)

        if docker_id is None:
            return self.dockers_pool.get_default_client()

        if self.dockers_pool.has_client_with_id(docker_id):
            # client can be None if it could not be loaded yet
            return self.dockers_pool.get_client_for_id(docker_id)

        raise ValueError(f"docker id {docker_id} is not defined")
