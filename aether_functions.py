# Copyright (C) 2018 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the "License");
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

from datetime import datetime
from enum import Enum
from functools import wraps
from hashlib import md5
import json
import logging
import sys

from aether.client import Client, AetherAPIException
from bravado.exception import HTTPBadGateway, BravadoConnectionError
import firebase_admin
from firebase_admin import db as RTDB
from firebase_admin import firestore as CFS
from google.cloud import firestore
from requests.exceptions import RequestException

from utils import Timeout

# Globals

AETHER_CONFIG_RTDB = '/_aether_config'
AETHER_SYNC_HASHES = '/_aether_hash'
AETHER_ERRORS = '/_aether_error'
CLIENTS = {}
ENTITIES = {}

# enums


class DB(Enum):
    Realtime = 1
    Firestore = 2


class Mode(Enum):
    SYNC = 1
    FORWARD = 2
    CONSUME = 3

# firebase connection


firebase_admin.initialize_app(options={
    'databaseURL': 'https://aether-kernel-gcp.firebaseio.com/'
})


# logging functions


def printf(msg):
    sys.stderr.write(str(msg) + "\n")
    logging.debug(msg)


def logged_operation(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        log_change(*args, **kwargs)
        return fn(*args, **kwargs)
    return wrapper


def log_change(*args, **kwargs):
    [printf(a) for a in args]

# utility functions


# def get_client(server_name):
#     global CLIENTS
#     if not CLIENTS.get(server_name):
#         settings = get_settings('_servers')
#         try:
#             setting = settings[server_name]
#         except KeyError:
#             raise KeyError(f'No configured server named {server_name}')
#         URL = setting['url']
#         USER = setting['user']
#         PW = setting['password']
#         with Timeout(length=2, caller='Client not connect to Aether'):
#             try:
#                 CLIENTS[server_name] = Client(URL, USER, PW)
#             except (BravadoConnectionError, HTTPBadGateway):
#                 raise RequestException(
#                     'Could not connect to Aether to get OpenAPI spec')

#     return CLIENTS[server_name]


# def get_entity(server_name):
#     global ENTITIES
#     if not ENTITIES.get(server_name):
#         client = get_client(server_name)
#         ENTITIES[server_name] = client.get_model('Entity')
#     return ENTITIES[server_name]


def get_settings(path):
    # get settings from RTDB
    full_path = '{base}/{extension}'.format(
        base=AETHER_CONFIG_RTDB,
        extension=path
    )
    return read_RTDB(full_path)


# def get_tracked(entity_path, db=DB.Realtime):
#     if db is DB.Realtime:
#         ext = 'rtdb'
#     else:
#         ext = 'cfs'
#     path = f'_tracked/{ext}'
#     settings = get_settings(path)
#     printf([path, settings])
#     for name, info in settings.items():
#         if info.get('path') in entity_path:
#             return info
#         else:
#             printf('{p} is not {ep}'.format(
#                 p=info.get('path'),
#                 ep=entity_path))
#     raise ValueError('no setting for {path} in {db}'.format(
#         path=path,
#         db=str(_type)
#     ))

# Aether Submission Functions


# def aether_upsert_entity(server_name, _id, entity_dict):
#     network_exceptions = (
#         TimeoutError,
#         RequestException,
#         Exception
#     )
#     try:
#         res = aether_create_entity(server_name, entity_dict)
#         return res
#     except network_exceptions:
#         printf("Server unavailable... aborting upsert")
#         return
#     except AetherAPIException:
#         printf("Couldn't create, attempting update")
#     try:
#         res = aether_update_entity(server_name, _id, entity_dict)
#         return res
#     except AetherAPIException:
#         printf("Couldn't update. API Error")
#         return None


# def aether_create_entity(server_name, entity_dict):
#     Entity = get_entity(server_name)
#     entity = Entity(**entity_dict)
#     client = get_client(server_name)
#     with Timeout(length=3, caller='Entity Creation Timeout'):
#         return client.entities.create(data=entity)


# def aether_update_entity(server_name, _id, entity_dict):
#     Entity = get_entity(server_name)
#     entity = Entity(**entity_dict)
#     client = get_client(server_name)
#     with Timeout(length=3, caller='Entity Update Timeout'):
#         return client.entities.update(id=_id, data=entity)

# RTDB Helpers


def write_RTDB(path, msg):
    ref = RTDB.reference(path)
    ref.set(msg)


def read_RTDB(path):
    obj = RTDB.reference(path).get()
    if not obj:
        raise ValueError(f'No object at path: {path}')
    return obj


def delete_RTDB(path):
    ref = RTDB.reference(path)
    return ref.delete()


def merge_delta(data):
    payload_data = data.get('data')  # .get(key, default) is not working here.
    if not payload_data:
        payload_data = {}
    delta = data.get('delta')
    if not delta:
        delta = {}
    payload_data.update(delta)
    if 'id' not in payload_data.keys():
        raise ValueError('All payloads must contain a UUID in the id field.')
    return payload_data


def save_hash(_id, msg):
    sorted_msg = json.dumps(msg, sort_keys=True)
    encoded_msg = sorted_msg.encode('utf-8')
    hash = str(md5(encoded_msg).hexdigest())[:16]
    path = f'{AETHER_SYNC_HASHES}/{_id}'
    write_RTDB(path, hash)
    return hash


def save_error(payload, context, server):
    _id = payload['id']
    msg = {
        'msg': payload,
        'srv': server,
        'path': context.resource,
        'timestamp': str(datetime.now().isoformat())
    }
    path = f'{AETHER_ERRORS}/{_id}'
    write_RTDB(path, msg)
    printf(f'wrote error to {_id}')

# Listener Functions


@logged_operation
def handle_update_CFS(data, context):
    pass
    # path_parts = context.resource.split('/documents/')[1].split('/')
    # collection_path = path_parts[0]
    # document_path = '/'.join(path_parts[1:])


# @logged_operation
# def handle_update_RTDB(data, context):
#     path = context.resource.split('/refs/')[1]
#     printf(path)
#     _type = DB.Realtime
#     try:
#         setting = get_tracked(path, _type)
#     except ValueError:
#         printf(f'No setting for path {path}; finished. Limit scope to save cloud function calls')
#         return
#     payload = merge_delta(data)
#     _id = payload['id']
#     mode = Mode[setting['sync_mode']]
#     if mode is not Mode.FORWARD:
#         save_hash(_id, payload)
#     if mode is Mode.CONSUME:
#         printf(f'Not sending type {path} since mode is {mode}')
#         return

#     submission = {
#         "id": _id,
#         "payload": payload,
#         "projectschema": setting['project_schema_id'],
#         "status": "Publishable"
#     }
#     res = aether_upsert_entity(setting['server'], _id, submission)
#     if not res:
#         printf('Upsert operation failed')
#         save_error(payload, context, setting['server'])
#         printf('Error Saved')

#     if mode is Mode.FORWARD:
#         delete_RTDB(path)
#         printf(f'deleted: {path} on Mode.FORWARD rule.')


@logged_operation
def handle_delete(data, context):
    pass


@logged_operation
def just_log(data, context):
    printf('just_logging')
    return 1


printf('Cold Start -- Main')
