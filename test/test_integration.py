#!/usr/bin/env python

# Copyright (C) 2020 by eHealth Africa : http://www.eHealthAfrica.org
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
# 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from multiprocessing import Queue
from uuid import uuid4


import pytest

# from . import cfs, rtdb  # noqa
from . import *  # noqa
from . import (  # noqa
    rtdb,
    cfs
)
from .app.fb_utils import (  # noqa
    RTDBTarget,
    InputManager,
    _NORMAL_CACHE,
    _QUARANTINE_CACHE,
    # cache
    cache_objects,
    remove_from_cache,
    get_cached_objects,
    list_cached_types,
    count_cached,
    # quarantine
    quarantine,
    get_quarantine_objects,
    list_quarantined_types,
    remove_from_quarantine,
    count_quarantined
)


@pytest.fixture(scope='session')
def TestRTDBTarget(rtdb):  # noqa
    yield RTDBTarget('test_project', rtdb)


@pytest.mark.integration
def test__crud_rtdb_target(TestRTDBTarget):
    _type = 'TEST1'
    _db = TestRTDBTarget
    _id = '1'
    path = f'nested/{_type}'
    msg = {'a': 'message'}

    _db.add(_id, path, msg)
    assert(msg['a'] == _db.get(_id, path)['a'])
    assert(_id in _db.list(path))
    _db.remove(_id, path)
    assert(_id not in _db.list(path))


@pytest.mark.integration
def test__crud_cfs(cfs):  # noqa
    _type = 'TEST2'
    _db = cfs
    _id = '1'
    path = f'type1/id1/{_type}'
    msg = {'a': 'message'}

    _db.write(path, msg, _id)
    assert(msg['a'] == _db.read(path, _id)['a'])
    assert(_id in _db.list(path))
    _db.remove(path, _id)
    assert(_id not in _db.list(path))


@pytest.mark.integration
def test__cache_operations(TestRTDBTarget):
    _type = 'TEST1'
    path = f'{_NORMAL_CACHE}/{_type}'
    docs = [{'id': x, 'val': str(uuid4())} for x in range(100)]
    q = Queue()
    cache_objects(_type, docs, q, TestRTDBTarget)
    assert(q.qsize() == 100)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 100)
    assert(_type in list_cached_types(TestRTDBTarget))
    q2 = Queue()
    get_cached_objects(_type, q2, TestRTDBTarget)
    assert(q2.qsize() == 100)
    while not q2.empty():
        doc = q2.get()
        remove_from_cache(_type, doc, TestRTDBTarget)
    assert(q2.qsize() == 0)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 0)


@pytest.mark.integration
def test__quarantine_operations(TestRTDBTarget):
    _type = 'TEST2'
    path = f'{_QUARANTINE_CACHE}/{_type}'
    docs = [{'id': x, 'val': str(uuid4())} for x in range(100)]
    quarantine(_type, docs, TestRTDBTarget)
    assert(count_quarantined(_type, TestRTDBTarget) == 100)
    assert(list_quarantined_types(TestRTDBTarget) == [_type])
    q2 = Queue()
    get_quarantine_objects(_type, q2, TestRTDBTarget)
    assert(q2.qsize() == 100)
    while not q2.empty():
        doc = q2.get()
        remove_from_quarantine(_type, doc, TestRTDBTarget)
    assert(q2.qsize() == 0)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 0)


@pytest.mark.integration
def test__load_prepared(loaded_cache, TestRTDBTarget):
    _type = 'xform-test'
    man = InputManager(TestRTDBTarget)
    _sets = man.get_inputs()
    _set = next(_sets)
    assert(_set.name == 'xform-test')
    assert(_set.docs.qsize() == 10)
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    assert(count_cached(_type, TestRTDBTarget) == 10)
