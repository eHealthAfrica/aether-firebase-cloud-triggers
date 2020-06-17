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
from dataclasses import dataclass
from enum import Enum
from multiprocessing import Queue
import json
from typing import (
    Any,
    Dict,
    List,
    Mapping
)

from firebase_admin.db import reference as rtdb_reference
from firebase_admin.firestore import client as cfs_client
from google.cloud import firestore
import spavro.schema
import spavro.io

from aether.python.avro import tools as avro_tools
from aet.logger import get_logger

from .config import get_function_config

CONF = get_function_config()
LOG = get_logger('Utils')


_SYNC_QUEUE = CONF.get('SYNC_PATH')
_NORMAL_CACHE = '_cached'
_QUARANTINE_CACHE = '_quarantined'


@dataclass
class InputSet:
    name: str
    docs: List[Any]
    options: Dict
    schema: Dict


class InputManager:
    rtdb: 'RTDBTarget'
    schemas: Dict[str, Dict]

    def __init__(self, rtdb_instance: 'RTDBTarget'):
        self.rtdb = rtdb_instance
        self.schemas = {}

    def _read_all(self):
        # even if there are no documents, we get a list of types
        # because the schemas and options are housed here.
        return self.rtdb.reference(_SYNC_QUEUE).get(shallow=False)

    def get_inputs(self) -> List[InputSet]:
        _inputs = self._read_all()
        for _type, obj in _inputs.items():
            schema = obj.get('schema')
            self.schemas[_type] = spavro.schema.parse(schema)
            docs = []
            # cached docs
            docs.extend(self._filter_good_objects(_type, self._checkout_cached(_type)))
            # new docs
            docs.extend(self._prepare_docs(_type, obj.get('documents', {}).items()))
            yield InputSet(
                name=_type,
                docs=docs,
                options=obj.get('options'),
                schema=schema
            )

    def _checkout_cached(self, _type):
        path = f'{_NORMAL_CACHE}/{_type}'
        docs = []

        doc_ids = self.rtdb.list(path=path)
        for _id in doc_ids:
            try:
                doc = self.rtdb.get(_id, path)
                # match convention from sync cache...
                docs.append([_id, json.dumps(doc)])
                self.rtdb.get(_id, path)
                self.rtdb.remove(_id, path)
            except Exception as err:
                LOG.debug(f'could not retrieve {_id} from {path}: {err}')
        return docs

    def _prepare_docs(self, _type, _docs):
        good_objects = self._filter_good_objects(_type, _docs)
        for _id, item in _docs:
            # delete from sync cache
            self._mark_copied(_type, _id)
        return good_objects

    def _filter_good_objects(self, _type, docs) -> List[Any]:
        passed = []
        failed = []
        for _id, _doc in docs:
            doc = json.loads(_doc)
            if spavro.io.validate(self.schemas[_type], doc):
                passed.append(doc)
            else:
                failed.append(doc)
                result = avro_tools.AvroValidator(
                    schema=self.schemas[_type],
                    datum=doc
                )
                for error in result.errors:
                    err_msg = avro_tools.format_validation_error(error)
                    LOG.error(f'Schema validation failed on type {_type}: {err_msg}')
        cache_objects(_type, passed, self.rtdb)
        quarantine(_type, failed, self.rtdb)
        return passed

    def _mark_copied(self, _type, _id):
        path = f'{_SYNC_QUEUE}/{_type}/documents/{_id}'
        self.rtdb.reference(path).delete()


# RTDB io

class RTDB(object):

    def __init__(self, app):
        self.app = app

    def reference(self, path):
        return rtdb_reference(path, app=self.app)


# CFS io

class Firestore(object):
    cfs: firestore.Client = None

    def __init__(self, app=None, instance=None):
        if app:
            self.cfs = cfs_client(app)
        elif instance:
            self.cfs = instance

    def read(self, path, _id=None, full_path=None):
        if full_path:
            return self.ref(full_path=full_path)
        if _id:
            return self.ref(path, _id).get().to_dict()
        else:
            return [i.to_dict() for i in self.ref(path, _id).get()]

    def ref(self, path, _id=None, full_path=None):
        if full_path:
            return self.cfs.document(full_path)
        if _id:
            path = f'{path}/{_id}'
            return self.cfs.document(path)
        else:
            return self.cfs.collection(path)

    def list(self, path):
        return [i.id for i in self.ref(path).list_documents()]

    def write(self, path, value, _id=None):
        return self.ref(path, _id).set(value)

    def remove(self, path, _id=None):
        return self.ref(path, _id).delete()


class RTDBTarget(object):

    def __init__(self, base_path: str = None, rtdb: RTDB = None):
        self.base_path = base_path
        self.rtdb = rtdb

    def add(self, _id, path, msg):
        path = f'{path}/{_id}'
        ref = self.reference(path)
        ref.set(json.dumps(msg))

    def get(self, _id, path):
        path = f'{path}/{_id}'
        _ref = self.reference(path)
        try:
            return json.loads(_ref.get())
        except (json.JSONDecodeError):
            return _ref.get()

    def reference(self, path):
        path = f'{self.base_path}/{path}'
        return self._raw_reference(path)

    def _raw_reference(self, path):
        return self.rtdb.reference(path)

    def remove(self, _id, path=None):
        path = f'{path}/{_id}'
        _ref = self.reference(path)
        return _ref.delete()

    def list(self, path=None):
        _ref = self.reference(path)
        res = _ref.get(shallow=True)
        if not res:
            return []
        return [i for i in res]


# generic cache operations

def _put(
    _type: str,
    objects: List[Any],
    rtdb_instance: RTDBTarget = None,
    _cache=_NORMAL_CACHE
):
    LOG.debug(f'Caching {len(objects)} objects')
    path = f'{_cache}/{_type}'
    try:
        for obj in objects:
            rtdb_instance.add(obj['id'], path, obj)
    except Exception as err:  # pragma: no cover
        LOG.critical(f'Could not save failed objects to RTDB {str(err)}')


def _get(_type: str, rtdb_instance: RTDBTarget = None, _cache=_NORMAL_CACHE) -> List[Any]:
    results = []
    path = f'{_cache}/{_type}'
    docs = rtdb_instance.list(path)
    for _id in docs:
        res = rtdb_instance.get(_id, path)
        if res:
            results.append(res)
        else:
            LOG.warning(f'Could not fetch object {_id} from path {path}')
    return results


def _remove(
    _type: str,
    obj: Mapping[Any, Any],
    rtdb_instance: RTDBTarget = None,
    _cache=_NORMAL_CACHE
):
    path = f'{_cache}/{_type}'
    _id = obj['id']
    try:
        rtdb_instance.remove(_id, path)
        return True
    except Exception as err:
        LOG.error(err)
        return False


def _list_types(
    _cache=_NORMAL_CACHE,
    rtdb_instance: RTDBTarget = None,
):
    return rtdb_instance.list(_cache)


# normal cache
def cache_objects(_type: str, objects: List[Any], rtdb_instance: RTDBTarget = None):
    return _put(_type, objects, rtdb_instance, _NORMAL_CACHE)


def remove_from_cache(_type: str, obj: Mapping[Any, Any], rtdb_instance: RTDBTarget = None):
    return _remove(_type, obj, rtdb_instance, _NORMAL_CACHE)


def get_cached_objects(_type: str, rtdb_instance: RTDBTarget = None) -> dict:
    return _get(_type, rtdb_instance, _NORMAL_CACHE)


def count_cached(_type: str, rtdb_instance: RTDBTarget = None) -> int:
    path = f'{_NORMAL_CACHE}/{_type}'
    return sum(1 for _ in rtdb_instance.list(path))


def list_cached_types(rtdb_instance: RTDBTarget = None):
    return _list_types(_NORMAL_CACHE, rtdb_instance)


# quarantine cache
def quarantine(_type: str, objects: List[Any], rtdb_instance: RTDBTarget = None):
    if objects:
        LOG.warning(f'Quarantine {len(objects)} objects')
        _put(_type, objects, rtdb_instance, _QUARANTINE_CACHE)


def get_quarantine_objects(_type: str, rtdb_instance: RTDBTarget = None) -> List[Any]:
    return _get(_type, rtdb_instance, _QUARANTINE_CACHE)


def remove_from_quarantine(_type: str, obj: Mapping[Any, Any], rtdb_instance: RTDBTarget = None):
    return _remove(_type, obj, rtdb_instance, _QUARANTINE_CACHE)


def list_quarantined_types(rtdb_instance: RTDBTarget = None):
    return _list_types(_QUARANTINE_CACHE, rtdb_instance)


def count_quarantined(_type: str, rtdb_instance: RTDBTarget = None) -> dict:
    path = f'{_QUARANTINE_CACHE}/{_type}'
    return sum(1 for _ in rtdb_instance.list(path))


def halve_iterable(obj):
    _size = len(obj)
    _chunk_size = int(_size / 2) + (_size % 2)
    for i in range(0, _size, _chunk_size):
        yield obj[i:i + _chunk_size]


def utf8size(obj) -> int:
    if not isinstance(obj, str):
        try:
            obj = json.dumps(obj)
        except json.JSONDecodeError:
            obj = str(obj)
    return len(obj.encode('utf-8'))


def sanitize_topic(topic):
    return ''.join(
        [i if i.isalnum() or i in ['-', '_', '.'] else '_' for i in topic]
    )
