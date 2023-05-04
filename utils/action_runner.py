import datetime
import logging
import tarfile
import tempfile

import docker
import docker.errors
import requests
from flask import abort, send_file

from utils.dockers_pool import DockersPool


class ActionRunner:
    def __init__(self, action, dockers_pool: DockersPool):
        self.dockers_pool = dockers_pool
        self.name = action['name']
        self.id = action['id']
        self.docker_image = action['image']
        self.command = action.get('command', None)
        self.volumes = action.get('volumes', None)
        self.volumes_from = action.get('volumes_from', None)
        self.devices = action.get('devices', None)
        self.artifacts = action.get('artifacts', None)
        self.privileged = action.get('privileged', None)
        self.environment = action.get('environment', None)
        self.network = action.get('network', None)
        self.network_mode = action.get('network_mode', None)
        self.user = action.get('user', None)
        self.working_dir = action.get('working_dir', None)

        self.docker_id = action.get('docker', None)

    def run(self):
        logging.info(f"executing action {self.name} / {self.id}")

        docker_client = \
            self.dockers_pool.get_client_for_id(self.docker_id) if self.docker_id \
                else self.dockers_pool.get_default_client()

        if not docker_client:
            logging.error("docker client not initialised")
            abort(500)

        params = {
            'auto_remove': False,
            'stream': True,
            'detach': True,
            'remove': False
        }

        if self.command:
            params['command'] = self.command
        if self.devices:
            params['devices'] = self.devices
        if self.environment:
            params['environment'] = self.environment
        if self.network:
            params['network'] = self.network
        if self.network_mode:
            params['network_mode'] = self.network_mode
        if self.privileged:
            params['privileged'] = self.privileged
        if self.user:
            params['user'] = self.user
        if self.volumes:
            params['volumes'] = self.volumes
        if self.volumes_from:
            params['volumes_from'] = self.volumes_from
        if self.working_dir:
            params['working_dir'] = self.working_dir

        try:
            cont = docker_client.containers.run(
                self.docker_image,
                **params,
            )

            cont.wait(timeout=120)

            if self.artifacts:
                tar_all_fp = tempfile.TemporaryFile()
                tar_all = tarfile.open(fileobj=tar_all_fp, mode="w:gz")

                for atf in self.artifacts:
                    with tempfile.TemporaryFile() as tmpfile:
                        raw_tar, stats = cont.get_archive(atf)
                        for chunk in raw_tar:
                            tmpfile.write(chunk)
                        tmpfile.flush()
                        tmpfile.seek(0)
                        tar_one = tarfile.open(fileobj=tmpfile, mode="r")
                        for tarinfo in tar_one:
                            one_file_in_tar = tar_one.extractfile(tarinfo)
                            tar_all.addfile(tarinfo, one_file_in_tar)

                tar_all.close()
                tar_all_fp.flush()
                tar_all_fp.seek(0)

                content = send_file(
                    tar_all_fp,
                    mimetype='application/gzip',
                    as_attachment=True,
                    last_modified=datetime.datetime.now(),
                    download_name='artifacts.tar.gz')
            else:
                content = cont.logs()
            cont.remove()
            return content
        except docker.errors.ImageNotFound:
            logging.error(f"image {self.docker_image} not found")
            abort(404)
        except docker.errors.APIError as err:
            logging.error(f"Docker API error: {err}")
            abort(500)
        except requests.exceptions.ReadTimeout:
            logging.error(f"timeout while running action {self.name}")
            abort(500)
