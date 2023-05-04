#!/usr/bin/env python3

import datetime
import json
import logging
import os
import sys
import threading

import time
import traceback
from functools import wraps
from typing import List
from json import JSONEncoder

import docker
import docker.errors

from pymongo import MongoClient

from flask import Flask, Blueprint, redirect, abort, request, Response, stream_with_context, session
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from waitress import serve
from flask_session import Session


from alarms.alarm import AlarmSeverity
from alarms.alarm_history import AlarmHistory
from alarms.composite_alarm import CompositeAlarmSender
from alarms.slack_alarm import SlackAlarmSender
from alarms.telegram_alarm import TelegramAlarmSender
from checkers.docker_checker import DockerChecker
from checkers.jmx_checker import JmxChecker
from checkers.web_service_checker import WebServiceChecker
from utils.action_runner import ActionRunner
from utils.config import Config
from utils.dockers_pool import DockersPool
from utils.restart_notification_manager import RestartNotificationManager
from utils.version import __version__, __api_version__

logging.basicConfig(
    format='%(asctime)s - %(module)s:%(name)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S')

logging.getLogger("urllib3").setLevel(logging.INFO)
logging.getLogger("docker").setLevel(logging.INFO)
logging.getLogger("slack_sdk").setLevel(logging.INFO)

settings = {
    'admin_mode': os.getenv('ADMIN_MODE', 'false').lower() in ('true', 'yes', '1'),
    'admin_username': os.getenv('ADMIN_USER', None),
    'admin_password': os.getenv('ADMIN_PASSWORD', None),
    'actions_enabled': os.getenv('ACTIONS_ENABLED', 'false').lower() in ('true', 'yes', '1')
}

main_instance = None


class Main:
    def __init__(self):
        self.jmx_checker = None
        self.docker_checker = None
        self.web_service_checker = None
        self.stop_flag = False

        if len(sys.argv) < 2 and not os.getenv(Config.EADOMO_CONFIG_ENV_NAME):
            print(f"usage: {sys.argv[0]} config1.yml config1.yml ... configN.yml")
            sys.exit(-1)

        all_configs = []

        if len(sys.argv) > 1:
            for cfg in sys.argv[1:]:
                if os.path.isfile(cfg):
                    all_configs.append(cfg)
                elif os.path.isdir(cfg):
                    dir_files = os.listdir(cfg)
                    for dir_file in dir_files:
                        if (dir_file.endswith('.yml') or dir_file.endswith('.yaml')) \
                                and os.path.isfile(dir_file):
                            all_configs.append(os.path.join(cfg, dir_file))
                else:
                    logging.warning(f"ignoring {cfg}: not a regular file or directory")
        logging.debug("configuration files: " + ",".join(all_configs))
        if os.getenv(Config.EADOMO_CONFIG_ENV_NAME):
            logging.debug(f"configuration will be loaded from environment variable "
                          f"{Config.EADOMO_CONFIG_ENV_NAME}")

        try:
            self.config = Config(all_configs)
        except ValueError as e:
            logging.error(f"fatal error: {e}")
            sys.exit(-1)

        mongo_uri = os.getenv("MONGO_URI", None)
        db_name = os.getenv("DB_NAME", None)
        self.mongodb_client = None
        self.mongo_db = None
        if mongo_uri is None or db_name is None:
            logging.warning("timeseries storage is disabled: "
                            "make sure you MONGO_URI and DB_NAME are set")
        else:
            self.mongodb_client = MongoClient(mongo_uri)
            logging.info(f"connected to mongo db at {mongo_uri}")
            self.mongo_db = self.mongodb_client[db_name]

        self.dockers_pool: DockersPool = DockersPool(self.config)

        self.log_alarm = AlarmHistory(self.mongo_db)
        self.telegram_alarm = TelegramAlarmSender()
        self.slack_alarm = SlackAlarmSender()
        self.composite_alarm = CompositeAlarmSender(
            [self.log_alarm, self.telegram_alarm, self.slack_alarm])

        self.composite_alarm.push_alarm(f"EaDoMo started", AlarmSeverity.INFO)

        self.restart_notification_manager = \
            RestartNotificationManager(self.mongo_db, self.composite_alarm)

        self.jmx_checker = JmxChecker(self.config, self.mongo_db, self.dockers_pool,
                                      self.composite_alarm,
                                      self.restart_notification_manager)
        self.docker_checker = DockerChecker(self.config, self.mongo_db, self.dockers_pool,
                                            self.composite_alarm,
                                            self.restart_notification_manager)
        self.web_service_checker = WebServiceChecker(self.config, self.mongo_db,
                                                     self.dockers_pool,
                                                     self.composite_alarm,
                                                     self.restart_notification_manager)

        self.checkers = []
        self.checkers.append(self.jmx_checker)
        self.checkers.append(self.docker_checker)
        self.checkers.append(self.web_service_checker)

        self.num_threads = len(self.checkers)
        self.threads: List[threading.Thread]
        self.threads = self.num_threads * [None]
        for i in range(0, self.num_threads):
            thread: threading.Thread
            thread = threading.Thread(
                target=Main.one_checker_thread,
                args=(self.checkers[i],))
            self.threads[i] = thread

        self.log_alarm.push_alarm('service started', AlarmSeverity.INFO)

    @staticmethod
    def one_checker_thread(checker):
        while not main_instance.stop_flag:
            try:
                checker.check()
                checker.store_status()
            except docker.errors.APIError as error:
                logging.error(error)
                traceback.print_exc()
            except OSError as error:
                logging.error(error)
                traceback.print_exc()
            except Exception as error:
                logging.error(error)
                traceback.print_exc()
            time.sleep(10)

    def start(self):
        thread: threading.Thread
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_flag = True

        for checker in self.checkers:
            checker.request_stop()

    def join(self, wait_time=5.0):
        thread: threading.Thread
        for thread in self.threads:
            thread.join(0.001)

        t_start = time.time()
        while time.time() - t_start < wait_time:
            has_alive = False
            for thread in self.threads:
                if thread.is_alive():
                    has_alive = True
                    break
            if not has_alive:
                break
            time.sleep(0.01)

    def get_docker_client_by_container_id(self, cont_id):
        for cont_config in self.config['blueprint']:
            if cont_config['name'] == cont_id:
                return self.docker_checker.get_docker_client_for_container(cont_config)

        raise docker.errors.NotFound(f"container {cont_id} not found")


class MyJSONEncoder(JSONEncoder):
    def default(self, o):
        obj = o
        try:
            if isinstance(obj, datetime.datetime):
                return obj.replace(tzinfo=datetime.timezone.utc).isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


class MyFlaskJSONEncoder(DefaultJSONProvider):
    def dumps(self, obj, *, option=None, **kwargs):
        return json.dumps(obj, cls=MyJSONEncoder)

    def loads(self, s, **kwargs):
        return json.loads(s)


app = Flask(__name__, static_folder='web/build')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
if os.getenv('SESSION_SECRET', None) is None:
    print("SESSION_SECRET is not set", file=sys.stderr)
    exit(-1)
app.secret_key = os.getenv('SESSION_SECRET')
app.json = MyFlaskJSONEncoder(app)
cors_origins = os.getenv('ALLOWED_CORS_ORIGINS', None)
if cors_origins is None:
    cors_origins = []
elif isinstance(cors_origins, str):
    cors_origins = cors_origins.split(',')
CORS(app, supports_credentials=True, origins=cors_origins)
bp = Blueprint('dashboard', __name__)
Session(app)


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


def my_static_rule(filename):
    if not os.path.exists(app.static_folder + '/' + filename):
        filename = 'index.html'
    return app.send_static_file(filename)


app.add_url_rule('/dashboard/<path:filename>',
                 endpoint='dashboard', view_func=my_static_rule)  # app.send_static_file


# authentication decorator
def admin_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        if not settings.get('admin_mode', False) or not session.get('is_admin', False):
            abort(403)
        return f(*args, **kwargs)
    return decorator


@bp.route("/status")
def print_status():
    return {
        'name': main_instance.config.get('name', 'unnamed'),
        'services': main_instance.web_service_checker.get_status(),
        'containers': main_instance.docker_checker.get_status(),
        'jmx': main_instance.jmx_checker.get_status(),
    }


def rebin(data, num_bins, start_time=None, end_time=None, container=None):
    if len(data) == 0:
        return []

    if start_time is None:
        start_time = data[0].get('timestamp', None)

    if end_time is None:
        end_time = data[-1].get('timestamp', None)

    values = []
    for t_point in data:
        t = t_point.get('timestamp', None)
        if container:
            if container in t_point['status']:
                status = t_point['status'][container].get('status', None)

                if t and status is not None:
                    values.append({'timestamp': t, 'status': status})
        else:
            for _, value in t_point['status'].items():
                status = value.get('status', None)

                if t and status is not None:
                    values.append({'timestamp': t, 'status': status})

    duration = end_time - start_time
    bin_duration = (duration / num_bins).total_seconds()
    bin_start = [None]*num_bins
    bin_end = [None]*num_bins
    bin_total = [0]*num_bins
    bin_failed = [0]*num_bins

    for i in range(0, num_bins):
        bin_start[i] = start_time + datetime.timedelta(seconds=i * bin_duration)
        bin_end[i] = start_time + datetime.timedelta(seconds=(i + 1) * bin_duration)

    for t_point in values:
        t = t_point['timestamp']
        if not t or t < start_time or t > end_time:
            continue

        for j in range(0, num_bins):
            if bin_start[j] <= t <= bin_end[j]:
                bin_total[j] += 1
                if t_point['status'] == 'NOK':
                    bin_failed[j] += 1

    bins = ['']*num_bins
    for i in range(0, num_bins):
        if bin_total[i] == 0:
            bins[i] = 'nostat'
            continue

        ratio_failed = bin_failed[i] / bin_total[i]
        status = 'warning'

        if ratio_failed == 0:
            status = 'allok'
        elif ratio_failed == 1:
            status = 'fatal'
        elif ratio_failed > 0.5:
            status = 'severe'

        bins[i] = status

    return bins


@bp.route('/status_timeseries')
def get_status_timeseries():
    num_bins = request.args.get('num_bins', default=24, type=int)
    if num_bins == 0:
        abort(400)
    hours_back = request.args.get('hours_back', default=24, type=int)
    now = datetime.datetime.now()
    start_time = now - datetime.timedelta(hours=hours_back)

    all_status = []

    for checker in main_instance.checkers:
        all_status.extend(checker.get_status_timeseries(start_time))

    for ts_point in all_status:
        for container in ts_point.get('status', []):
            ts_point['status'][container].pop('stats', None)
            ts_point['status'][container].pop('user_defined', None)

    all_status.sort(key=lambda x: x['timestamp'])

    return rebin(all_status, num_bins, start_time=start_time, end_time=now)


@bp.route('/container/<container>/status_timeseries')
def get_status_timeseries_for_container(container):
    num_bins = request.args.get('num_bins', default=24, type=int)
    if num_bins == 0:
        abort(400)
    hours_back = request.args.get('hours_back', default=24, type=int)
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=hours_back)
    ts = main_instance.docker_checker.get_status_timeseries_for_container(container, start_time)
    return rebin(ts, num_bins, container=container, start_time=start_time, end_time=end_time)


@bp.route('/container/<container>/<stat>')
def get_stats_for_container(container, stat):
    return main_instance.docker_checker.get_stats_for_container(container, stat)


def gen_icon(color, width=None, height=None):
    width = 20 if width is None else width
    height = 10 if height is None else height

    icon = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" 
width="{width}px" height="{height}px">
<g><rect x="0" y="0" width="{width}" height="{height}" style="fill:{color}"/></g></svg>
    '''
    return icon


@bp.route("/container/<container>/status_icon")
def get_container_status_icon(container):
    status = main_instance.docker_checker.get_status()
    cont_status = status.get(container, {})
    status_ind = cont_status.get('status', None)
    last_failure = cont_status.get('last_failure', None)

    return get_element_status_icon(request, status_ind, last_failure)


def get_element_status_icon(req, status_ind, last_failure):
    width = req.args.get('width', 20)
    height = req.args.get('height', 10)

    red = "rgb(255,0,0)"
    yellow = "rgb(255,255,0)"
    green = "rgb(0,255,0)"
    grey = "rgb(150,150,150)"

    svg_mime_type = 'image/svg+xml'

    if status_ind is None:
        return Response(gen_icon(grey, width, height), mimetype=svg_mime_type)

    if status_ind != 'OK':
        return Response(gen_icon(red, width, height), mimetype=svg_mime_type)

    if last_failure is None:
        return Response(gen_icon(green, width, height), mimetype=svg_mime_type)

    last_failure = datetime.datetime.fromisoformat(last_failure)

    yellow_last_failure_threshold = int(os.getenv("YELLOW_LAST_FAILURE_THRESHOLD", "60"))

    if datetime.datetime.now(datetime.timezone.utc) - last_failure < \
            datetime.timedelta(minutes=yellow_last_failure_threshold):
        return Response(gen_icon(yellow, width, height), mimetype=svg_mime_type)

    return Response(gen_icon(green, width, height), mimetype=svg_mime_type)


@bp.route("/service/<service>/status_icon")
def get_service_status_icon(service):
    status = main_instance.web_service_checker.get_status()
    cont_status = status.get(service, {})
    status_ind = cont_status.get('status', None)
    last_failure = cont_status.get('last_failure', None)

    return get_element_status_icon(request, status_ind, last_failure)


@bp.route('/service/<service>/status_timeseries')
def get_timeseries_for_service(service):
    num_bins = request.args.get('num_bins', default=24, type=int)
    if num_bins == 0:
        abort(400)
    hours_back = request.args.get('hours_back', default=24, type=int)
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=hours_back)
    ts = main_instance.web_service_checker.get_status_timeseries_for_service(service, start_time)
    return rebin(ts, num_bins, container=service, start_time=start_time, end_time=end_time)


@bp.route('/service/<service>/<stat>')
def get_stats_for_service(service, stat):
    return main_instance.web_service_checker.get_stats_for_service(service, stat)


@bp.route('/jmx/<container>/status_timeseries')
def get_status_timeseries_for_jmx_service(container):
    num_bins = request.args.get('num_bins', default=24, type=int)
    if num_bins == 0:
        abort(400)
    hours_back = request.args.get('hours_back', default=24, type=int)
    ts = main_instance.jmx_checker.get_status_timeseries_for_service(container)
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=hours_back)
    return rebin(ts, num_bins, container=container, start_time=start_time, end_time=end_time)


@bp.route('/jmx/<container>/<stat>')
def get_stats_for_jmx_service(container, stat):
    return main_instance.jmx_checker.get_stats_for_service(container, stat)


@bp.route('/jmx/user_defined/<container>/<parname>')
def get_user_defined_param_for_jmx_service(container, parname):
    return main_instance.jmx_checker.get_user_defined_param_for_service(container, parname)


@bp.route("/log")
def print_history_log():
    return main_instance.log_alarm.get_log()


@bp.route("/docker/ids")
@admin_required
def get_docker_ids():
    return main_instance.dockers_pool.get_all_ids()


@bp.route("/docker/<docker_id>/prune-containers")
@admin_required
def prune_containers(docker_id):
    client = main_instance.dockers_pool.get_client_for_id(docker_id)
    try:
        return client.containers.prune()
    except docker.errors.APIError:
        abort(500)


@bp.route("/docker/<docker_id>/prune-images")
@admin_required
def prune_images(docker_id):
    client = main_instance.dockers_pool.get_client_for_id(docker_id)
    try:
        return client.images.prune()
    except docker.errors.APIError:
        abort(500)


@bp.route("/docker/<docker_id>/images")
@admin_required
def list_docker_images(docker_id):
    client = main_instance.dockers_pool.get_client_for_id(docker_id)
    try:
        all_images = client.images.list()

        return [x.attrs for x in all_images]
    except docker.errors.APIError:
        abort(500)


@bp.route("/docker/<docker_id>/containers")
@admin_required
def list_docker_containers(docker_id):
    client = main_instance.dockers_pool.get_client_for_id(docker_id)
    try:
        all_cont = client.containers.list()

        return [x.attrs for x in all_cont]
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/log")
def get_container_log(container):
    limit = request.args.get('limit')
    limit = int(limit) if limit is not None else 1000
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        logs = cont.logs(tail=limit)
        if isinstance(logs, bytes):
            logs = logs.decode("utf-8")
        if isinstance(logs, str):
            num_lines = len(logs.split("\n"))
            return {
                'truncated': num_lines > limit,
                'log': logs
            }
        if isinstance(logs, list):
            num_lines = len(logs)
            return {
                'truncated': num_lines > limit,
                'log': "\n".join(logs)
            }
        return {
            'truncated': False,
            'log': ""
        }
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/inspect")
@admin_required
def get_container_inspect(container):
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        return cont.attrs
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/inspect-image")
@admin_required
def get_container_inspect_image(container):
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        image = cont.image
        return image.attrs
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/env")
@admin_required
def get_container_env(container):
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        env = cont.attrs['Config']['Env']
        return env
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/restart")
@admin_required
def container_restart(container):
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        cont.restart()
        return "OK"
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/full-log")
def get_container_full_log(container):
    try:
        client = main_instance.get_docker_client_by_container_id(container)
        cont = client.containers.get(container)
        log_generator = cont.logs(stream=True, follow=False)
        return Response(stream_with_context(log_generator),
                        headers={'Content-Disposition': f'attachment; filename={container}.log'})
    except docker.errors.NotFound:
        abort(404)
    except docker.errors.APIError:
        abort(500)


@bp.route("/container/<container>/notify-restart")
def notify_container_restart(container):
    notify_restart(container, "container", request)

    return "OK"


@bp.route("/jmx/<service>/notify-restart")
def notify_jmx_restart(service):
    notify_restart(service, "jmx", request)

    return "OK"


@bp.route("/service/<service>/notify-restart")
def notify_service_restart(service):
    notify_restart(service, "service", request)

    return "OK"


@bp.route("/restart-notifications")
def print_restart_notifications():
    return main_instance.restart_notification_manager.list_notifications()


@bp.route("/get-readme")
def get_readme():
    return main_instance.config.get('readme', None)


@bp.route("/version")
def get_version():
    commit_id = os.getenv("COMMIT_ID", "-unknown-")
    return {'version': __version__, 'commit': commit_id, 'api_version': __api_version__}


@bp.route("/admin-mode")
def get_admin_mode_enabled():
    return str(settings.get('admin_mode', False) and session.get('is_admin', False)).lower()


@bp.route("/actions-enabled")
def get_actions_enabled():
    return str(settings.get('actions_enabled', False)).lower()


def notify_restart(affected_object, obj_type, req):
    t0 = datetime.datetime.now()
    t1 = t0 + datetime.timedelta(hours=1)
    valid_from = req.args.get('valid_from')
    if valid_from is not None:
        t0 = datetime.datetime.fromisoformat(valid_from)
    valid_until = req.args.get('valid_from')
    if valid_until is not None:
        t1 = datetime.datetime.fromisoformat(valid_until)
    valid_for = req.args.get('valid_for')  # validity interval in minutes
    if valid_for is not None:
        if valid_until is not None:
            logging.error("parameters valid_for and valid_until cannot be specified at the same time")
            abort(400)
        t1 = t0 + datetime.timedelta(minutes=int(valid_for))

    main_instance.restart_notification_manager.add_notification(affected_object, obj_type, t0, t1)


@bp.route("/get-actions")
def get_all_actions():
    if not settings.get('actions_enabled', False):
        return []

    if not session.get('is_admin', False):
        return []

    return [
        {
            'name': x['name'],
            'id': x['id'],
            'icon': x['icon'],
            'hasArtifacts': len(x.get('artifacts', [])) > 0
        }
        for x in main_instance.config['actions']]


@bp.route("/action/<action_id>/invoke")
@admin_required
def invoke_action(action_id):
    this_action = [x for x in main_instance.config['actions'] if x['id'] == action_id]
    if not this_action:
        abort(404)
    this_action = this_action[0]
    action_runner = ActionRunner(this_action, main_instance.dockers_pool)
    return action_runner.run()


@bp.route("/")
def index_page():
    return redirect("/dashboard/index.html", code=302)


@bp.route("/login", methods=['POST'])
def login():
    admin_username = settings.get('admin_username', None)
    admin_password = settings.get('admin_password', None)

    if not admin_username or not admin_password:
        abort(403)

    username = request.form['username']
    password = request.form['password']

    if username == admin_username and password == admin_password:
        session['username'] = admin_username
        session['is_admin'] = True
        return "OK"

    abort(403)


@bp.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    return "OK"


app.register_blueprint(bp, url_prefix='/'+os.getenv('SCRIPT_NAME', 'dashboard'))


if __name__ == '__main__':
    main_instance = Main()

    port = int(os.getenv('PORT', '5555'))
    bind_to = os.getenv('BIND_TO', '127.0.0.1')

    main_instance.start()

    if os.getenv('DEBUG', '0').lower() in ('0', 'false', 'no'):
        serve(app, host=bind_to, port=port)
    else:
        app.run(host=bind_to, port=port, debug=True, use_reloader=False)
    logging.info("web server stopped")
    main_instance.stop()
    main_instance.join()
    if main_instance.mongodb_client:
        main_instance.mongodb_client.close()
    os._exit(0)
