import logging
import docker
import docker.errors

from utils.version import __version__


class DockersPool:
    DEFAULT_ID = '~DEFAULT~'

    class FutureConnection:
        def __init__(self, docker_id, base_url):
            self.docker_id = docker_id
            self.base_url = base_url

        def reinit_client(self):
            use_ssh = self.base_url and self.base_url.startswith('ssh:')

            try:
                if self.base_url:
                    client = docker.DockerClient(
                        base_url=self.base_url,
                        use_ssh_client=use_ssh,
                        user_agent='EaDoMo/' + __version__)
                else:
                    client = docker.from_env()
                return client
            except docker.errors.APIError as error:
                logging.error(f"failed to connect to docker {self.docker_id}: {str(error)}")
            except OSError as error:
                logging.error(f"failed to connect to docker {self.docker_id}: {str(error)}")
            except docker.errors.DockerException as e:
                logging.error(f"failed to connect to docker {self.docker_id}: {str(e)}")
            return self

    def __init__(self, config):
        self.config = config
        self.default_docker_client = None
        self._init_dockers()

    def has_client_with_id(self, client_id):
        if client_id == DockersPool.DEFAULT_ID:
            return self.default_docker_client is not None

        return client_id in self.docker_clients

    def get_client_for_id(self, client_id):
        if client_id == DockersPool.DEFAULT_ID:
            return self.get_default_client()

        if isinstance(self.docker_clients[client_id], DockersPool.FutureConnection):
            self.docker_clients[client_id] = self.docker_clients[client_id].reinit_client()

        if isinstance(self.docker_clients[client_id], DockersPool.FutureConnection):
            return None

        return self.docker_clients[client_id]

    def get_default_client(self):
        if isinstance(self.default_docker_client, DockersPool.FutureConnection):
            self.default_docker_client = self.default_docker_client.reinit_client()

        if isinstance(self.default_docker_client, DockersPool.FutureConnection):
            return None

        return self.default_docker_client

    def get_all_ids(self):
        return list(self.docker_clients) + [DockersPool.DEFAULT_ID]

    def _init_dockers(self):
        self.docker_clients = {}
        self.default_docker_client = None

        first_client = None

        for docker_conn in self.config.get('dockers', []):
            docker_id = docker_conn['id']
            if docker_id == DockersPool.DEFAULT_ID:
                raise ValueError(f"cannot use id {DockersPool.DEFAULT_ID} - reserved for default")
            is_default = docker_conn.get('default', False)
            base_url: str = docker_conn.get('url', None)

            use_ssh = base_url and base_url.startswith('ssh:')

            try:
                if base_url:
                    client = docker.DockerClient(
                        base_url=base_url,
                        use_ssh_client=use_ssh,
                        user_agent='EaDoMo/' + __version__)
                else:
                    client = docker.from_env()
            except docker.errors.DockerException as e:
                logging.error(f"failed to connect to docker {docker_id}: {str(e)}")
                client = DockersPool.FutureConnection(docker_id, base_url)

            if not isinstance(client, DockersPool.FutureConnection):
                info = client.info()
                logging.info(f"connected to docker engine at {info.get('Name','-unknown-')}, "
                             f"version {info.get('ServerVersion','-unknown-')}")

            self.docker_clients[docker_id] = client

            if first_client is None:
                first_client = client

            if is_default:
                if self.default_docker_client:
                    raise ValueError("cannot have more than one default docker clients")
                self.default_docker_client = client

        if self.default_docker_client is None:
            if first_client:
                self.default_docker_client = first_client
                logging.warning(f"no default docker client defined: "
                                f"using {self.default_docker_client.info().get('Name', '-')}")
            else:
                logging.warning("no default docker client: using from env")
                self.default_docker_client = docker.from_env()

        if not isinstance(self.default_docker_client, DockersPool.FutureConnection):
            logging.info(f"default docker client: "
                            f"using {self.default_docker_client.info().get('Name', '-')}")
