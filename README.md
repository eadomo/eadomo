# EaDoMo - Easy Docker Monitoring

EaDoMo is a good choice if you don't want to spend days configuring enterprise-level monitoring frameworks
like Prometheus, Zabbix or similar. It is designed for small non-production deployments
and allows you to have an overview of the docker containers and services running within your ecosystem.

EaDoMo is easy to install and easy to run. The only thing it requires to operate is a connection to your Docker
socket. Apart from docker containers, EaDoMo can also monitor servers (also those which have a zabbix agent installed)
and Java applications providing access to JMX.

EaDoMo uses MongoDB to store data. It can inform you about service outages using Telegram and Slack channels.

EaDoMo has two access levels: a normal access level allowing you to monitor your containers without exposing
sensitive information like environment variables, and admin access level, giving access to more sensitive details
and allowing to perform a set of privileged actions.

## Running

The recommended way to run EaDoMo is using docker - directly or via docker-compose.

To monitor local host:
```shell
docker run -d -v /var/run/docker.sock:/var/run/docker.sock \
  -v $PWD/eadomo.yml:/etc/eadomo.yml \
  --net=host \  # not required, only to simplify host ports monitoring
  --restart unless-stopped \
  -p 5555:5555 \
  --name eadomo \
  --env-file env.env \
  eadomo/eadomo:latest python3 eadomo.py /etc/eadomo.yml
```

A sample env file:
```shell
ENV_NAME=my-deployment
ADMIN_MODE=1
ADMIN_USER=admin
ADMIN_PASSWORD=secure_password
ACTIONS_ENABLED=1
SESSION_SECRET=random-string
MONGO_URI=mongodb://localhost
DB_NAME=depl_status
ALLOWED_CORS_ORIGINS=https://your.host.com
TELEGRAM_CHAT_ID=12345  # optional, only if telegram is used
TELEGRAM_TOKEN=your-telegram-token # optional, only if telegram is used
SLACK_CHAT=my-system-notifications # optional, only if slack is used
SLACK_TOKEN=your-slack-app-token # optional, only if slack is used
```

To monitor remote host (EaDoMo can also monitor several docker hosts - see below):
```shell
docker run -d -e DOCKER_HOST=ssh://1.2.3.4:22 \
  -v $PWD/eadomo.yml:/etc/eadomo.yml \
  --restart unless-stopped \
  -p 5555:5555 \
  --name eadomo \
  --env-file env.env \
  eadomo/eadomo:latest python3 eadomo.py /etc/eadomo.yml
```

Or with docker-compose.yml:

```yaml
version: '3.5'
services:
  eadomo:
    image: eadomo/eadomo
    ports:
      - "5555:5555"
    volumes:
      - ./eadomo.yml:/etc/eadomo.yml
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      ENV_NAME: my-deployment
      ADMIN_MODE: 1
      ADMIN_USER: admin
      ADMIN_PASSWORD: secure_password
      ACTIONS_ENABLED: 1
      SESSION_SECRET: random-string
      MONGO_URI: mongodb://mongo
      DB_NAME: depl_status
      ALLOWED_CORS_ORIGINS: https://your.host.com
      TELEGRAM_CHAT_ID: 12345  # optional, only if telegram is used
      TELEGRAM_TOKEN: your-telegram-token # optional, only if telegram is used
      SLACK_CHAT: my-system-notifications # optional, only if slack is used
      SLACK_TOKEN: your-slack-app-token # optional, only if slack is used

  mongo:
    image: mongo:4
    volumes:
      - mongo:/data/db

volumes:
  mongo:
```

By default EaDoMo exposes port 5555 as an unencrypted HTTP connection and is available in /dashboard context:
`http://your-host:5555/dashboard`.
If you want HTTPS, please run it behind a reverse proxy, for instance, NGINX.

## Checks performed

### Docker containers

EaDoMo verifies the following parameters of docker containers:
* if the container running
* if the container has been restarted recently (planned/unplanned)
* if a port exposed is open and listening
* if disk space is below a threshold
* if a newer image is available
* (on gitlab) if new commits were pushed into the development branch which are not on deployment branch yet

It also gathers statistics on:
* uptime
* memory used
* CPU used
* disk usage
* network traffic

### Web services
EaDoMo verifies:
* if a port is listening
* SSL certificate validity

### JMX services
EaDoMo gathers statistics on:
* uptime
* memory used
* CPU used
* disk usage
* network traffic

## Configuration details

EaDoMo is configured in two ways: using environment variables and using deployment description files.

### Environment variables
The following environment variables can be used:

| Variable name                | Meaning                                            | Default value |
|:-----------------------------|:---------------------------------------------------|:--------------|
| MONGO_URI                    | Mongo URI                                          ||
| DB_NAME                      | Name of the Mongo database                         ||
| ALLOWED_CORS_ORIGINS         | Allow CORS origins - host where EaDoMo is deployed ||
| SESSION_SECRET               | Random string to encrypt session storage           |||DOCKER_HOST|URL of the docker API|local unix socket||
| TELEGRAM_CHAT_ID             | Telegram chat ID                                   ||
| TELEGRAM_TOKEN               | Telegram token                                     |
| SLACK_TOKEN                  | Slack App token                                    ||
| SLACK_CHAT                   | Slack channel name                                 ||
| ACTIONS_ENABLED              | Enable actions                                     | false         |
| ADMIN_MODE                   | Enable admin mode                                  | false         |
| ADMIN_PASSWORD               | Admin password                                     ||
| ADMIN_USER                   | Admin user                                         ||
| ENV_NAME                     | Name of the environment - used in messages         ||
| EADOMO_CONFIGURATION         | Content of the configuration (same as files)       ||
| DEFAULT_DISK_USAGE_THRESHOLD | Default disk usage threshold in %                  | 80            |

### Deployment configuration

EaDoMo expects you to describe your container and service layout in a YML file. 
You can use several files passing them all as command line arguments to `eadomo.py`, or you can use a directory - then
all files found in this directory will be interpreted as configuration file.
You can also set environment variable `EADOMO_CONFIGURATION` with the content of a configuration file.

| L1           | L2                  | L3                | L4        | L5       | Description                                                    | Mandatory | Default               |
|:-------------|:--------------------|:------------------|-----------|----------|:---------------------------------------------------------------|-----------|-----------------------|
| name         |                     |                   |           |          | Name of the deployment                                         |           |                       |
| enabled      |                     |                   |           |          | `true` if this configuration file is enabled                   |           | true                  |
| dockers      |                     |                   |           |          | List of dockers to use                                         |           |                       |
|              | id                  |                   |           |          | Identifier                                                     | ✓         |                       |
|              | url                 |                   |           |          | Docker Url<br/>Can be also unix:/// or ssh://                  | ✓         |                       |
|              | default             |                   |           |          | Set to true if it's the default docker (use only once)         |           |                       |
| blueprint    |                     |                   |           |          | Container layout                                               |           |                       |
| *list of ->* | name                |                   |           |          | Container name                                                 | ✓         |                       |
|              | docker              |                   |           |          | Identifier of docker to use                                    |           | Default docker client |
|              | friendly-name       |                   |           |          | Container friendly name                                        |           |                       |
|              | desc                |                   |           |          | Description                                                    |           |                       |
|              | panel               |                   |           |          | Link to control panel or a service                             |           |                       |
|              | ports               |                   |           |          | List of ports to check                                         |           |                       | 
|              | disk-free           |                   |           |          | Disk free checks (overriding defaults)                         |           |                       | 
|              |                     | mount             |           |          | Mount point                                                    | ✓         |                       |
|              |                     | threshold         |           |          | Disk usage threshold in %                                      | ✓         |                       |
|              | image-update-check  |                   |           |          | Check registry to image updates                                |           |                       |
|              |                     | username          |           |          | Registry username                                              | ✓         |                       |
|              |                     | password          |           |          | Registry password                                              | ✓         |                       |
|              | gitlab-update-check |                   |           |          | Check GitLab for new commits                                   |           |                       |
|              |                     | url               |           |          | GitLab URL                                                     | ✓         |                       |
|              |                     | token             |           |          | GitLab private token for API access                            | ✓         |                       |
|              |                     | project-id        |           |          | GitLab project id                                              | ✓         |                       |
|              |                     | dev-branch        |           |          | Development branch                                             | ✓         |                       |
|              |                     | deploy-branch     |           |          | Deployment branch                                              | ✓         |                       |
| jmx          |                     |                   |           |          | JMX monitoring of Java services                                |           |                       |
| *list of ->* | service             |                   |           |          | Name of the service                                            | ✓         |                       |
|              | panel               |                   |           |          | Link to control panel                                          |           |                       |
|              | docker              |                   |           |          | Identifier of docker to use                                    |           | Default docker client |
|              | url                 |                   |           |          | Service locator                                                |           |                       |
|              |                     | docker            |           |          | Use to located service in a docker container                   |           |                       |
|              |                     |                   | container |          | Name of the container                                          |           |                       |
|              |                     |                   | port      |          | JMX port                                                       |           |                       |
| services     |                     |                   |           |          | Services layout                                                |           |                       |
| *list of ->* | name                |                   |           |          | Service name                                                   |           |                       |
|              | hostname            |                   |           |          | Hostname                                                       |           |                       |
|              | panel               |                   |           |          | Link to control panel                                          |           |                       |
|              | docker              |                   |           |          | Identifier of docker to use                                    |           | Default docker client |
|              | endpoints           |                   |           |          | Endpoints to check                                             |           |                       |
| *list of ->* |                     | url               |           |          | Endpoint URL                                                   | ✓         |                       |
|              |                     | type              |           |          | Check type: direct (from host) or docker                       |           | docker                |
|              |                     | method            |           |          | Access method (GET, POST, etc.)                                |           | GET                   |
|              |                     | data              |           |          | Data to send to the server (POST and PUT only)                 |           |                       |
|              |                     | extra_headers     |           |          | Additional headers for the HTTP request (dictionary)           |           |                       |
|              |                     | extra_curl_params |           |          | Additional parameters to pass to cURL                          |           |                       |
| *list of ->* |                     | exp_code          |           |          | Expected HTTP return code                                      |           | 200                   |
|              |                     | auth              |           |          | Authentication                                                 |           |                       |
|              |                     |                   | basic     |          | Basic authentication                                           |           |                       |
|              |                     |                   |           | username | Username                                                       | ✓         |                       |
|              |                     |                   |           | password | Password                                                       | ✓         |                       |
|              | zabbix              |                   |           |          | Zabbix configuration                                           |           |                       |
|              |                     | disk-free         |           |          | Disk free checks                                               |           |                       | 
|              |                     |                   | mount     |          | Mount point                                                    | ✓         |                       |
|              |                     |                   | threshold |          | Disk usage threshold in %                                      | ✓         |                       |
|              |                     | mount-points      |           |          | List of mount points to monitor (if default threshold is used) |           |                       |
|              |                     | ports             |           |          | List of ports to check                                         |           |                       | 
|              |                     | nic               |           |          | List of network interfaces to monitor                          |           |                       | 
| actions      |                     |                   |           |          | Actions which can be executed from the UI                      |           |                       | 
| *list of ->* | name                |                   |           |          | Action name                                                    |           |                       | 
|              | id                  |                   |           |          | Action identifier (to be used in the URL)                      |           |                       | 
|              | docker              |                   |           |          | Identifier of docker to user                                   |           | Default docker client |
|              | icon                |                   |           |          | Action icon                                                    |           |                       | 
|              | image               |                   |           |          | Docker image to run in                                         |           |                       | 
|              | working_dir         |                   |           |          | Working directory                                              |           |                       | 
|              | environment         |                   |           |          | List of environment variables                                  |           |                       | 
|              | volumes             |                   |           |          | Volumes to mount                                               |           |                       | 
|              | volumes_from        |                   |           |          | Mount volumes from another container                           |           |                       | 
|              | network             |                   |           |          | Docker network                                                 |           |                       | 
|              | network_mode        |                   |           |          | Docker network mode                                            |           |                       | 
|              | privileged          |                   |           |          | Privileged mode                                                |           |                       | 
|              | user                |                   |           |          | User to run as                                                 |           |                       | 
|              | command             |                   |           |          | Command to execute                                             |           |                       | 
|              | artifacts           |                   |           |          | List of artifacts to send to the user after actions completion |           |                       | 
| readme       |                     |                   |           |          | Text to shown in the Read me tab                               |           |                       | 

### Sample configuration

```yaml
name: Sample Deployment
dockers:  # optional; if not specified is detected automatically
  - id: default
    default: true
    url: unix:///var/run/docker.sock
  - id: server1
    url: ssh://server1
blueprint:
  - name: backend-staging-00
    panel: https://staging.mydomain.com/api/ # swagger
    src: https://gitlab.mydomain.com/backend/backend
    desc: Sample backend server
    friendly-name: backend 0
    image-update-check:
      username: !ENV ${GITLAB_DOCKER_USERNAME}
      password: !ENV ${GITLAB_DOCKER_PASSWORD}
    ports:
      - 3000
    gitlab-update-check:
      url: https://gitlab.mydomain.com
      token: !ENV ${GITLAB_PRIVATE_TOKEN}
      project-id: 123
      dev-branch: main
      deploy-branch: production
  - name: frontend-staging
    panel: https://staging.mydomain.com/ # app page
    src: https://gitlab.mydomain.com/frontend/frontend
    desc: Sample frontend server
    friendly-name: frontend
    image-update-check:
      username: !ENV ${GITLAB_DOCKER_USERNAME}
      password: !ENV ${GITLAB_DOCKER_PASSWORD}
    ports:
      - 8080
    gitlab-update-check:
      url: https://gitlab.mydomain.com
      token: !ENV ${GITLAB_PRIVATE_TOKEN}
      project-id: 456
      dev-branch: main
      deploy-branch: production
  - name: service-a-staging
    docker: server1
    panel: https://staging.mydomain.com/admin/service-a # service admin panel
    src: https://gitlab.mydomain.com/services/service-a
    desc: Sample service A
    friendly-name: service-a
    image-update-check:
      username: !ENV ${GITLAB_DOCKER_USERNAME}
      password: !ENV ${GITLAB_DOCKER_PASSWORD}
    ports:
      - 9000
    gitlab-update-check:
      url: https://gitlab.mydomain.com
      token: !ENV ${GITLAB_PRIVATE_TOKEN}
      project-id: 567
      dev-branch: main
      deploy-branch: production

services:
  - name: gitlab
    panel: https://gitlab.mydomain.com/
    endpoints:
      - url: https://gitlab.mydomain.com/users/sign_in
        method: GET
        exp_code:
          - 200

jmx:
  - service: kafka
    panel: https://staging.mydomain.com/admin/kafka-ui/
    url:
      docker:
        container: kafka1
        port: 10167
    mbeans:
     - name: kafka.cluster:type=Partition,name=LastStableOffsetLag,topic=backend-interactions,partition=0
       our-alias: Last stable offset lag
       metric-name: kafka_cluster_Partition_LastStableOffsetLag
       conv: x * 1

actions:
  - name: show host disk space
    docker: server1
    id: df1
    icon: DeviceHdd
    image: busybox:latest
    volumes:
      - /:/host
    command: df -h /host

readme: |
    This is a sample deployment. 

```

## Advanced topics

### Autodiscovery
If you don't want to start from scratch, you can use EaDoMo autodiscovery function. You need first to specify docker 
daemon to connect to using environment variable DOCKER_HOST or just passing the socket as a volume. Then, when executed,
it will go through all containers and print contents of the configuration YAML file representing your system.

An example of autodiscovery call to use local docker server:
```shell
docker run --rm -it -e -v /var/run/docker.sock:/var/run/docker.sock eadomo/eadomo autodiscovery.py
```

An example of autodiscovery call to use a remote docker daemon:
```shell
docker run --rm -it -e DOCKER_HOST=tcp://1.2.3.4:2375 eadomo/eadomo autodiscovery.py
```

An example of autodiscovery call to use a remote docker daemon via ssh:
```shell
docker run --rm -it -e DOCKER_HOST=ssh://1.2.3.4:22 eadomo/eadomo autodiscovery.py
```

### Using environment variables in the config YML file

EaDoMo supports usage of environment variables in the configuration YML files - this is useful
for instance to avoid hard-coding access credentials. 
The following notation shall be used to substitute environment variables in the YML file:

`!ENV ${NAME_OF_YOUR_VARIABLE}`

for instance

```YAML
token: !ENV ${GITLAB_PRIVATE_TOKEN}
```

### Service downtime notification

EaDoMo supports planned service downtime notifications and lowers severity of messages about the service unavailability from "ALARM"
to "INFO" if a downtime falls within an announced time window. The notification is done using a call like this:
```shell
curl -sS https://EADOMON-URL/dashboard/container/CONTAINER-NAME/notify-restart
```

You can optionally provide query string arguments `valid_from` (ISO8601 format) and `valid_for` (integer number of minutes);
otherwise the validity interval will be from now for one hour.

### Automatic commit monitoring

EaDoMo can monitor for you a GitLab instance and show a special icon (green lighting) next to a container, service or 
JMX application if there are new commits in the development branch which are not yet merged to a deployment branch.
Please use parameters in the "gitlab-update-check" for that.

### Security

EaDoMo requires access to docker daemon to be able to perform the monitoring tasks. This access
allows full control over the service and often the whole host, often equal to the root level access.
This means that you have to be very careful with the access permissions and the way you deploy EaDoMo.
The best practice is not to deploy EaDoMo on the internet, keep it within your internal LAN.
If you put it on the internet, we recommend several levels of protection: Basic Authentication,
IP-address filtering, client-side certificate (or even a hardware token).

Be also extremely careful with the admin level access to EaDoMo: it allows access to environment variables,
which often contain sensitive data like passwords.

### Integrating status icon into your web page

You can integrate container or service status as obtained from EaDoMo into your own web page.
For that purpose EaDoMo exposes endpoints `/container/<container_name>/status_icon` and
`/service/<service_name>/status_icon`. They return SVG icon in the color corresponding to the 
service status (green, yellow, red or grey). Optionally, you can supply `width` and `height` parameters.

For example:
```https://my.server.com/dashboard/container/postgres/status_icon?width=100&height=100```

## Under the hood

Docker engine provides itself a lot of monitoring and statistics gathering capabilities, which EaDoMo is making
use of. Monitoring of services is done either by simple checking open port availability or, in case Zabbix agent
is available, by fetching node information from it. For JMX applications EaDoMo launches a proxy container
within the target container namespace which fetches information and provides it to EaDoMo via Docker connection -
there is no additional communication channels opened between the monitored host and the host where EaDoMo is running.

## License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction(s), including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit person(s) to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contacts

info at eadomo.com
