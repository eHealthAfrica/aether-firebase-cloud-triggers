# Copyright (C) 2020 by eHealth Africa : http://www.eHealthAfrica.org
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

from collections import namedtuple
from enum import Enum
from multiprocessing import Queue
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    NamedTuple,
    Union
)

from firebase_admin.db import reference as realtime
from firebase_admin.firestore import client as cfs
from google.cloud import firestore

_logger = settings.get_logger('Utils')


class CacheType(Enum):
    NORMAL = 1
    QUARANTINE = 2
    NONE = 3


_NORMAL_CACHE = 'exm_failed_submissions'
_QUARANTINE_CACHE = 'exm_quarantine_submissions'
_FAILED_CACHES = [
    (CacheType.NORMAL, _NORMAL_CACHE),
    (CacheType.QUARANTINE, _QUARANTINE_CACHE),
]

Constants = namedtuple(
    'Constants',
    (
        'mappings',
        'mappingsets',
        'schemas',
        'schemadecorators',
        'submissions',
        'schema_id',
        'schema_definition',
    )
)


# RTDB io

class RTDB(object):

    def __init__(self, app):
        self.app = app

    def reference(self, path):
        return realtime(path, app=self.app)


# CFS io

def Firestore(app) -> firestore.Client:
    # we use firebase_admin.firestore which takes the app info and returns firestore.Client
    return cfs(app)


def cfs_ref(cfs, path, doc_id=None):
    if doc_id:
        path = f'{path}/{doc_id}'
        return cfs.document(path)
    else:
        return cfs.collection(path)


def read_cfs(cfs, path, doc_id=None):
    if doc_id:
        return cfs_ref(cfs, path, doc_id).get().to_dict()
    else:
        return [i.to_dict() for i in cfs_ref(cfs, path, doc_id).get()]


def write_cfs(cfs, path, value, doc_id=None):
    return cfs_ref(cfs, path, doc_id).set(value)


def reference_path(fn):
    def wrap(*args, **kwargs):
        base_path = args[0].base_path
        if 'path' not in kwargs:
            raise RuntimeError('path not specified for RTDB operation')
        kwargs['path'] = f'{base_path}/' + kwargs['path']
        return fn(*args, **kwargs)
    return wrap


class RTDB_Target(object):
    '''
    add(obj, partial_path (_NORMAL_CACHE))
    get(_id, partial_path (_NORMAL_CACHE))
    remove(_id, _NORMAL_CACHE)
    exists(_id, partial_path (_NORMAL_CACHE))
    list(_NORMAL_CACHE)
    '''
    def __init__(self, base_path: str = None, rtdb: RTDB = None):
        self.path = base_path
        self.rtdb = rtdb

    def add(self, _id, path, msg):
        path = f'{self.base_path}/{path}/{_id}'
        ref = self.rtdb.reference(path)
        ref.set(msg)

    def get(self, _id, path):
        path = f'{self.base_path}/{path}/{_id}'
        _ref = self.rtdb.reference(path)
        return _ref.get()

    def remove(self, _id, path=None):
        path = f'{self.base_path}/{path}/{_id}'
        _ref = self.rtdb.reference(path)
        return _ref.delete()

    def list(self, path=None):
        path = f'{self.base_path}/{path}'
        _ref = self.rtdb.reference(path)
        return [i for i in _ref.get(shallow=True)]


def cache_objects(objects: List[Any], queue: Queue, rtdb_instance=None):
    _logger.debug(f'Caching {len(objects)} objects')

    try:
        for obj in objects:
            rtdb_instance.add(obj['id'], _NORMAL_CACHE, obj)
            queue.put(obj)
    except Exception as err:  # pragma: no cover
        _logger.critical(f'Could not save failed objects to RTDB {str(err)}')


def get_failed_objects(queue: Queue, rtdb_instance=None) -> dict:
    failed = rtdb_instance.list(_NORMAL_CACHE)
    for _id in failed:
        res = rtdb_instance.get(_id, _NORMAL_CACHE)
        if res:
            queue.put(res)
        else:
            _logger.warning(f'Could not fetch object {_id}')


def remove_from_cache(obj: Mapping[Any, Any], rtdb_instance=None):
    _id = obj['id']
    try:
        rtdb_instance.remove(_id, _NORMAL_CACHE)
        return True
    except Exception as err:
        _logger.error(err)
        raise err


def quarantine(objects: List[Any], rtdb_instance=None):
    _logger.warning(f'Quarantine {len(objects)} objects')

    try:
        for obj in objects:
            rtdb_instance.add(obj['id'], _QUARANTINE_CACHE, obj)
    except Exception as err:  # pragma: no cover
        _logger.critical(f'Could not save quarantine objects RTDB {str(err)}')


def remove_from_quarantine(obj: Mapping[Any, Any], rtdb_instance=None):
    _id = obj['id']
    try:
        rtdb_instance.remove(_id, _QUARANTINE_CACHE)
        return True
    except Exception as err:
        _logger.error(err)
        raise err


def count_quarantined(rtdb_instance=None) -> dict:
    return sum(1 for _ in rtdb_instance.list(_QUARANTINE_CACHE))


def halve_iterable(obj):
    _size = len(obj)
    _chunk_size = int(_size / 2) + (_size % 2)
    for i in range(0, _size, _chunk_size):
        yield obj[i:i + _chunk_size]
