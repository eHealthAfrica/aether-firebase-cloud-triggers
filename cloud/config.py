#!/usr/bin/env python

# Copyright (C) 2018 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from aet.settings import Settings

function_config = None
kafka_config = None

kafka_admin_uses = {
    'bootstrap.servers': 'KAFKA_URL',
    'security.protocol': 'KAFKA_SECURITY_PROTOCOL',
    'sasl.mechanism': 'KAFKA_SASL_MECHANISM',
    'sasl.username': 'KAFKA_SASL_USERNAME',
    'sasl.password': 'KAFKA_SASL_PASSWORD'
}


def load_config():
    global function_config
    function_config = Settings()
    load_kafka_config()


def load_kafka_config():
    global kafka_config
    kafka_config = Settings()
    for key, env in kafka_admin_uses.items():
        kafka_config[key.upper()] = kafka_config.get(env)


def get_kafka_admin_config():
    kafka_security = get_kafka_config().copy()
    ks_keys = list(kafka_security.keys())
    for i in ks_keys:
        if i.lower() not in kafka_admin_uses.keys():
            del kafka_security[i]
        else:
            kafka_security[i.lower()] = kafka_security[i]
            del kafka_security[i]
    return kafka_security


def get_kafka_config():
    return kafka_config


def get_function_config():
    return function_config


load_config()
