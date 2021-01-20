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

from time import sleep  # noqa
from uuid import uuid4  # noqa


import pytest

# from . import cfs, rtdb  # noqa
from . import *  # noqa
from . import (  # noqa
    rtdb,
    cfs,
    delete_topic,
    get_admin_client,
    TENANT,
    KADMIN,
    KAFKA_SECURITY,
    CONF,
    LOG,
    TEST_DOC_COUNT
)

from .app.cloud import exporter  # noqa
from .app.cloud.fb_move import (  # noqa
    requires_sync,
    _make_wildcard_writer,
    _make_doc_getter,
    DBType,
    Mode
)
from .app.cloud.fb_utils import (  # noqa
    RTDBTarget,
    InputManager,
    InputSet,
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
from .app.cloud import kafka_utils  # noqa


class FakeContext:

    def __init__(self, res_path):
        self.resource = res_path


def _make_fake_context(path):
    return FakeContext(path)


@pytest.fixture(scope='session')
def TestRTDBTarget(rtdb):  # noqa
    yield RTDBTarget('test_project', rtdb)


@pytest.mark.integration
def test__requires_sync(rtdb):  # noqa
    _type = 'TEST1'
    _id = '1'
    path = f'nested/{_type}'
    msg = {'a': 'message'}
    assert(requires_sync(_id, _type, msg, rtdb) is True)
    assert(requires_sync(_id, _type, msg, rtdb) is False)

    path = f'_hash/{_type}/{_id}'
    rtdb.reference(path).delete()


@pytest.mark.parametrize('source,data,expected,use_delta,context_resource', [
    (DBType.CFS, {'value': 'a'}, None, None, '/some/documents/_path/to/a/doc_id'),
    (DBType.RTDB, {'value': 'a', 'delta': 'b'}, 'b', True, '/some/refs/_path/to/a/doc_id'),
    (DBType.RTDB, {}, None, False, '/some/refs/_path/to/a/doc_id')  # no matching doc
])
@pytest.mark.integration
def test__doc_getter(rtdb, source, data, expected, use_delta, cfs, context_resource):  # noqa
    context = _make_fake_context(context_resource)
    _fn = _make_doc_getter(source, rtdb, use_delta, cfs)
    assert(_fn(data, context) == expected)


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
    docs = []
    for x in range(100):
        _id = str(uuid4())
        docs.append((
            _id,
            {'id': _id, 'val': _id}
        ))
    cache_objects(_type, docs, TestRTDBTarget)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 100)
    assert(_type in list_cached_types(TestRTDBTarget))
    q2 = get_cached_objects(_type, TestRTDBTarget)
    assert(len(q2) >= 100)
    for doc in q2:
        remove_from_cache(_type, doc, TestRTDBTarget)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 0)


@pytest.mark.integration
def test__quarantine_operations(TestRTDBTarget):
    _type = 'TEST2'
    path = f'{_QUARANTINE_CACHE}/{_type}'
    docs = []
    for x in range(100):
        _id = str(uuid4())
        docs.append((
            _id,
            {'id': _id, 'val': _id}
        ))
    quarantine(_type, docs, TestRTDBTarget)
    assert(count_quarantined(_type, TestRTDBTarget) == 100)
    assert(_type in list_quarantined_types(TestRTDBTarget))
    q2 = get_quarantine_objects(_type, TestRTDBTarget)
    assert(len(q2) >= 100)
    for doc in q2:
        remove_from_quarantine(_type, doc, TestRTDBTarget)
    assert(sum(1 for _ in TestRTDBTarget.list(path)) == 0)


@pytest.mark.integration
def test__load_prepared(load_cache, TestRTDBTarget):
    # using the loaded_cache fixture loads the cache (on every use)
    _type = 'xform-test'
    load_cache(_type, TEST_DOC_COUNT)
    man = InputManager(TestRTDBTarget)
    _sets = man.get_inputs()
    _set: InputSet = next(_sets)
    assert(_set.name == _type)
    assert(len(_set.docs) == TEST_DOC_COUNT)
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    assert(count_cached(_type, TestRTDBTarget) == TEST_DOC_COUNT)


@pytest.mark.integration
def test__load_cached(TestRTDBTarget):
    _type = 'xform-test'
    assert(count_cached(_type, TestRTDBTarget) == TEST_DOC_COUNT)
    man = InputManager(TestRTDBTarget)
    _sets = man.get_inputs()
    _set: InputSet = next(_sets)
    assert(_set.name == _type)
    assert(len(_set.docs) == TEST_DOC_COUNT)
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    assert(count_cached(_type, TestRTDBTarget) == TEST_DOC_COUNT)


def _exhaust_consumer(consumer, expected_count, expected_topic):
    while True:
        LOG.debug('looking for expected topic')
        meta = consumer.list_topics(timeout=3)
        if meta:
            if expected_topic in meta.topics.keys():
                break
        LOG.debug('waiting for kafka to populate')
    _all_messages = []
    for x in range(30):
        messages = consumer.poll_and_deserialize(timeout=1, num_messages=1)
        for msg in messages:
            _all_messages.append(msg)
        # read messages and check masking
        if len(_all_messages) == expected_count:
            LOG.debug(f'found {len(_all_messages)}')
            break
        else:
            LOG.debug(f'still only {len(_all_messages)}')
    return _all_messages


@pytest.mark.integration
def test__publish_kafka(consumer, TestRTDBTarget):
    _type = 'xform-test'
    _topic_name = f'{TENANT}.fbs.{_type}'
    man = InputManager(TestRTDBTarget)
    _sets = man.get_inputs()
    _input: InputSet = next(_sets)
    assert(len(_input.docs) > 0)
    _ct = kafka_utils.publish(
        _input.docs,
        _input.schema,
        _input.name,
        TestRTDBTarget,
        10_000
    )
    assert(_ct == 0)  # messages over limit, all quarantined?
    assert(count_quarantined(_type, TestRTDBTarget) == TEST_DOC_COUNT)
    # clear it
    TestRTDBTarget.reference(f'{_QUARANTINE_CACHE}/{_type}').delete()
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    _ct = kafka_utils.publish(
        _input.docs,
        _input.schema,
        _input.name,
        TestRTDBTarget,
        100_000
    )
    assert(_ct == TEST_DOC_COUNT)
    assert(count_cached(_type, TestRTDBTarget) == 0)
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    consumer.subscribe([_topic_name])
    consumer.seek_to_beginning()
    messages = _exhaust_consumer(consumer, TEST_DOC_COUNT, _topic_name)
    assert(len(messages) == TEST_DOC_COUNT)
    delete_topic(KADMIN, _topic_name)


@pytest.mark.integration
def test__exporter(load_cache, consumer, TestRTDBTarget):
    _type = 'xform-test-1'
    load_cache(_type, TEST_DOC_COUNT)
    _topic_name = f'{TENANT}.fbs.{_type}'
    app = exporter.ExportManager(TestRTDBTarget)
    app.run()
    consumer.subscribe([_topic_name])
    consumer.seek_to_beginning()
    messages = _exhaust_consumer(consumer, TEST_DOC_COUNT, _topic_name)
    assert(len(messages) == TEST_DOC_COUNT)
    assert(count_cached(_type, TestRTDBTarget) == 0)
    assert(count_quarantined(_type, TestRTDBTarget) == 0)
    delete_topic(KADMIN, _topic_name)
