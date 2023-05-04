#!/usr/bin/env python3

import logging
import re

import yaml
import docker
import docker.errors


def discover_jmx(cont):
    try:
        top = cont.top()
    except docker.errors.APIError as error:
        logging.error(error)
        return 0

    titles = top.get('Titles', [])
    procs = top.get('Processes', None)
    idx_cmd = titles.index('CMD')
    idx_pid = titles.index('PID')
    if idx_cmd < 0 or idx_pid < 0 or procs is None:
        return 0
    java_found = False
    ports = set()
    for proc in procs:
        cmd_line = proc[idx_cmd]
        pid = proc[idx_pid]
        if '/java' in cmd_line:
            java_found = True
            m = re.match(r'^.*com\.sun\.management\.jmxremote\.port\s*=\s*(\d+).*$', cmd_line)
            if m:
                port = int(m.group(1))
                return port

            placeholder = '{}'
            pid_socket_inodes = []
            try:
                find_output = cont.client.containers.run(
                    "debian:bullseye", f'find /hostproc/{pid}/fd -lname "socket*" -exec readlink {placeholder} \\;',
                    volumes=['/proc:/hostproc'],
                    remove=True,
                    privileged=True)
                sockets = find_output.decode('utf-8').strip().split("\n")
                for socket in sockets:
                    m = re.match(r'^socket:\[(\d+)\]$', socket)
                    if m:
                        socket_inode = m.group(1)
                        pid_socket_inodes.append(int(socket_inode))
            except docker.errors.APIError as error:
                logging.error(error)
                pid_socket_inodes = None

            (exit_code, output) = cont.exec_run("cat /proc/net/tcp", privileged=True)
            if exit_code != 0:
                continue
            tcp_stat = output.decode('utf-8').split("\n")

            # find all ports open for listen on 0.0.0.0
            for line in tcp_stat[1:]:
                cols = line.strip().split()
                if not cols:
                    continue
                st = cols[3]
                local_addr = cols[1]
                inode = int(cols[9])
                if pid_socket_inodes is not None and inode not in pid_socket_inodes:
                    continue
                (ip, port) = local_addr.split(':')
                if ip == '00000000' and int(st, 16) == 10:
                    port = int(port, 16)
                    ports.add(port)
    if ports:
        return list(ports)
    return None if java_found else 0


def create_autodiscovered_config():
    docker_client = docker.from_env()
    info = docker_client.info()
    remote_name = info.get('Name', '-unknown-')
    remote_version = info.get('ServerVersion', '-unknown-')
    print(f"# discovered docker at {docker_client.api.base_url}: {remote_name} {remote_version}")
    while True:
        try:
            running_cont = docker_client.containers.list()
            break
        except docker.errors.NotFound as e:  # list() fails if a container has been stopped
            logging.error(e)

    cont_desc = []
    jmx_desc = []

    for cont in running_cont:
        try:
            logging.info(f"found container {cont.name}")
            non_standard_registry = False
            for img_tag in cont.image.tags:
                try:
                    if img_tag.split(':')[0].index('.') >= -0:
                        non_standard_registry = True
                except ValueError:
                    pass
            rec = {
                'name': cont.name,
                'ports': [int(x.rstrip('/tcp')) for x in cont.ports if x.endswith('/tcp')]
            }
            if len(rec['ports']) == 0:
                del rec['ports']
            if non_standard_registry:
                rec['image-update-check'] = {'username': '!ENV ${REGISTRY_USER}',
                                             'password': '!ENV ${REGISTRY_PASSWORD}'}
            jmx_port = discover_jmx(cont)

            if jmx_port != 0:
                if jmx_port is None:
                    port_str = 'TODO: specify JMX port (often 1099)'
                elif isinstance(jmx_port, list):
                    port_str = ','.join(map(str, jmx_port))
                    port_str = 'TODO: specify JMX port; Java process opens ports: '+port_str
                else:
                    port_str = jmx_port
                jmx_desc.append({
                    'service': cont.name,
                    'url': {
                        'docker': {
                            'container': cont.name,
                            'port': port_str
                        }
                    }
                })
            cont_desc.append(rec)
        except docker.errors.NotFound:
            logging.error(f"container {cont.name} is gone")
            continue

    compiled = {
        'name': f'Auto-discovered configuration at {remote_name}',
        'blueprint': cont_desc,
        'jmx': jmx_desc,
        'services': []
    }

    print(yaml.dump(compiled, indent=4))


if __name__ == "__main__":
    create_autodiscovered_config()
