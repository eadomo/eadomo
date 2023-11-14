import hashlib
import logging
import os
import re
from typing import List

import yaml
import mergedeep

from jsonschema import validate
import jsonschema.exceptions

pattern = re.compile(r'.*?\${(\w+)}.*?')

schema = {
    "$id": "https://eadomo.com/configuration.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "EaDoMo Configuration",
    "type": "object",
    "required": [],
    "$defs": {
        "docker": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "url": {"type": "string"},
                "default": {"type": "boolean"}
            },
            "additionalProperties": False
        },
        "container": {
            "type": "object",
            "required": [],
            "properties": {
                "name": {"type": "string"},
                "desc": {"type": "string"},
                "friendly-name": {"type": "string"},
                "docker": {"type": "string"},
                "panel": {"type": "string"},
                "src": {"type": "string"},
                "ports": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 65535}},
                "disk-free": {"type": "array", "items": {"$ref": "#/$defs/df"}},
                "gitlab-update-check": {"$ref": "#/$defs/gitlab-update-check"},
                "image-update-check": {"$ref": "#/$defs/image-update-check"}
            },
            "additionalProperties": False
        },
        "jmxsrv": {
            "type": "object",
            "required": ["service"],
            "properties": {
                "service": {"type": "string"},
                "desc": {"type": "string"},
                "panel": {"type": "string"},
                "docker": {"type": "string"},
                "url": {"$ref": "#/$defs/jmxurl"},
                "src": {"type": "string"},
                "mbeans": {"type": "array", "items": {"$ref": "#/$defs/mbean"}}
            },
            "additionalProperties": False
        },
        "service": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "desc": {"type": "string"},
                "panel": {"type": "string"},
                "src": {"type": "string"},
                "hostname": {"type": "string"},
                "ports": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 65535}},
                "endpoints": {"type": "array", "items": {"$ref": "#/$defs/endpoint"}},
                "zabbix": {"$ref": "#/$defs/zabbix"}
            },
            "additionalProperties": False
        },
        "action": {
            "type": "object",
            "required": ["name", "command"],
            "properties": {
                "name": {"type": "string"},
                "command": {"type": "string"},
                "docker": {"type": "string"},
                "id": {"type": "string"},
                "icon": {"type": "string"},
                "image": {"type": "string"},
                "network": {"type": "string"},
                "network_mode": {"type": "string"},
                "privileged": {"type": "boolean"},
                "user": {"type": "string"},
                "volumes_from": {"type": "string"},
                "working_dir": {"type": "string"},
                "volumes": {"type": "array", "items": {"type": "string"}},
                "devices": {"type": "array", "items": {"type": "string"}},
                "environment": {"type": "array", "items": {"type": "string"}},
                "artifacts": {"type": "array", "items": {"type": "string"}}
            },
            "additionalProperties": False
        },
        "df": {
            "type": "object",
            "required": ["mount", "threshold"],
            "properties": {
                "mount": {"type": "string"},
                "threshold": {"type": "number", "minimum": 0, "maximum": 100}
            },
            "additionalProperties": False
        },
        "gitlab-update-check": {
            "type": "object",
            "required": ["url", "token", "project-id", "dev-branch", "deploy-branch"],
            "properties": {
                "url": {"type": "string"},
                "token": {"type": "string"},
                "project-id": {"type": "integer"},
                "dev-branch": {"type": "string"},
                "deploy-branch": {"type": "string"}
            },
            "additionalProperties": False
        },
        "image-update-check": {
            "type": "object",
            "required": [],
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "additionalProperties": False
        },
        "jmxurl": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["docker"],
                    "properties": {"docker": {"$ref": "#/$defs/jmxdockerurl"}},
                    "additionalProperties": False
                },
                {
                    "type": "object",
                    "required": ["direct"],
                    "properties": {"direct": {"type": "string"}},
                    "additionalProperties": False
                },
            ]
        },
        "jmxdockerurl": {
            "type": "object",
            "required": ["container", "port"],
            "properties": {
                "container": {"type": "string"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535}
            },
            "additionalProperties": False
        },
        "mbean": {
            "type": "object",
            "required": ["name", "metric-name"],
            "properties": {
                "name": {"type": "string"},
                "our-alias": {"type": "string"},
                "metric-name": {"type": "string"},
                "conv": {"type": "string"}
            },
            "additionalProperties": False
        },
        "endpoint": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string"},
                "data": {"type": "string"},
                "extra_curl_params": {"type": "string"},
                "auth": {"$ref": "#/$defs/httpauth"},
                "type": {"type": "string", "enum": ["direct", "docker"]},
                "exp_code": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 999}}
            },
            "additionalProperties": False
        },
        "httpauth": {
            "type": "object",
            "required": [],
            "properties": {
                "basic": {"$ref": "#/$defs/http-basic-auth"}
            },
            "additionalProperties": False
        },
        "http-basic-auth": {
            "type": "object",
            "required": [],
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"}
            },
            "additionalProperties": False
        },
        "zabbix": {
            "type": "object",
            "required": [],
            "properties": {
                "ports": {"type": "array", "items": {"type": ["integer", "string"]}},
                "disk-free": {"type": "array", "items": {"$ref": "#/$defs/df"}},
                "mount-points": {"type": "array", "items": {"type": "string"}},
                "nic": {"type": "array", "items": {"type": "string"}}
            },
            "additionalProperties": False
        }
    },
    "properties": {
        "name": {"type": "string"},
        "enabled": {"type": "boolean"},
        "dockers": {"type": "array", "items": {"$ref": "#/$defs/docker"}},
        "blueprint": {"type": "array", "items": {"$ref": "#/$defs/container"}},
        "jmx": {"type": "array", "items": {"$ref": "#/$defs/jmxsrv"}},
        "services": {"type": "array", "items": {"$ref": "#/$defs/service"}},
        "actions": {"type": "array", "items": {"$ref": "#/$defs/action"}},
        "readme": {"type": "string"}
    },
    "additionalProperties": False
}


def yaml_cons_resolv_env_vars(yaml_loader, node):
    loaded_yaml = yaml_loader.construct_scalar(node)
    m = pattern.findall(loaded_yaml)
    if m:
        resolved_yaml = loaded_yaml
        for env_name in m:
            if env_name not in os.environ:
                raise ValueError(f"environment variable {env_name} referred "
                                 f"in the layout configuration file is not set")
            resolved_yaml = resolved_yaml.replace(
                f'${{{env_name}}}', os.getenv(env_name)
            )
        loaded_yaml = resolved_yaml
    return loaded_yaml


class Config:
    EADOMO_CONFIG_ENV_NAME = "EADOMO_CONFIGURATION"

    def __init__(self, all_config_files: List[str]):
        self.config = {}

        tag = '!ENV'

        if os.getenv(Config.EADOMO_CONFIG_ENV_NAME):
            loader = yaml.loader.SafeLoader
            loader.add_implicit_resolver(tag, pattern, None)
            loader.add_constructor(tag, yaml_cons_resolv_env_vars)
            this_config = yaml.load(os.getenv(Config.EADOMO_CONFIG_ENV_NAME), loader)

            if this_config.get('enabled', True):
                validate(instance=this_config, schema=schema)
                mergedeep.merge(self.config, this_config, strategy=mergedeep.Strategy.ADDITIVE)

        for config_file in all_config_files:
            with open(config_file, encoding='utf-8') as f:
                loader = yaml.loader.SafeLoader
                loader.add_implicit_resolver(tag, pattern, None)
                loader.add_constructor(tag, yaml_cons_resolv_env_vars)
                this_config = yaml.load(f, loader)

                if this_config.get('enabled', True):
                    try:
                        validate(instance=this_config, schema=schema)
                    except jsonschema.exceptions.ValidationError as e:
                        logging.error(f"{config_file} loading failed: {e}")
                        raise ValueError from e
                    mergedeep.merge(self.config, this_config, strategy=mergedeep.Strategy.ADDITIVE)
        if self.config.get('services', None) is None:
            self.config['services'] = []
        if self.config.get('blueprint', None) is None:
            self.config['blueprint'] = []
        if self.config.get('actions', None) is None:
            self.config['actions'] = []

        for action in self.config['actions']:
            if 'id' not in action:
                m = hashlib.sha256()
                m.update(action['name'].encode('utf-8'))
                action['id'] = m.hexdigest()[0:8]
            elif not action['id'].isalnum():
                raise ValueError(f"action id \"{action['id']}\" is invalid: it may contain only letters and numbers")

    def __getitem__(self, key):
        return self.config[key]

    def get(self, key, default=None):
        return self.config.get(key, default)
