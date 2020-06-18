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

import json
import pytest
import spavro.schema

from aether.python.avro import tools as avro_tools

from .fixtures import *  # noqa
from . import LOGIAK_SCHEMA, LOGIAK_ENTITY, LOG
# from .aether_functions import *  # noqa
from .app.cloud.fb_utils import halve_iterable, sanitize_topic
from .app.cloud import fb_move
from .app.cloud.config import get_kafka_config, kafka_admin_uses, get_kafka_admin_config
from .app.cloud.hash import make_hash
from .app.cloud.schema_utils import coersce, coersce_or_fail


@pytest.mark.unit
def test__kafka_config():
    _conf = get_kafka_config()
    for k in kafka_admin_uses.keys():
        assert(_conf.get(k) is not None)
    _conf = get_kafka_admin_config()
    assert(set(_conf.keys()) == set(kafka_admin_uses.keys()))


@pytest.mark.parametrize('test,expected', [
    ('%topic', '_topic'),
    ('Someother.topic', 'Someother.topic'),
    ('a_third&option', 'a_third_option')
])
@pytest.mark.unit
def test__sanitize_topic_name(test, expected):
    assert(sanitize_topic(test) == expected)


@pytest.mark.unit
def test__path_resolution():
    resolver = fb_move._path_grabber('/{deployment_id}/data/{doc_type}/{doc_id}')
    res = resolver('projects/covid19-logiak/databases/(default)/documents/293cfe55-d45d-4ceb-a4c0-d01623e4850b/data/patient/a7b0f5db-d2b8-4356-a33d-c0ed62238a9f')  # noqa
    assert(res['deployment_id'] == '293cfe55-d45d-4ceb-a4c0-d01623e4850b')
    assert(res['doc_type'] == 'patient')
    assert(res['doc_id'] == 'a7b0f5db-d2b8-4356-a33d-c0ed62238a9f')


@pytest.mark.unit
def test__fixture(simple_payload):
    assert(True)


@pytest.mark.unit
def test__event_reverse():
    evt = EventType.WRITE
    db = DatabaseType.CFS
    descriptor = event_from_type(db, evt)
    t_db, t_evt = info_from_event(descriptor)
    assert(evt is t_evt)
    assert(db is t_db)


@pytest.mark.unit
def test__contextualize(simple_entity):
    gen = simple_entity(10)
    evt = EventType.WRITE
    db = DatabaseType.CFS
    for e in gen:
        res = contextualize(e, evt, db)
        assert(
            res.get('context').get('eventType') == event_from_type(db, evt)
        )
        assert(
            res.get('data').get('body') == e.payload['body']
        )


@pytest.mark.unit
def test__halve_iterable():
    a = [1, 2, 3, 4, 5]
    b, c = halve_iterable(a)
    assert(len(b) == 3)
    assert(len(c) == 2)


@pytest.mark.unit
def test__hash():
    _type_a = 'a'
    _type_b = 'b'
    doc_a = {'a': 'value', 'list': [1, 2, 3]}
    doc_b = {'a': 'value', 'list': [2, 1, 3]}
    doc_c = {'a': 'value', 'list': [2, 1]}
    assert(make_hash(_type_a, doc_a) == make_hash(_type_a, doc_a))
    assert(make_hash(_type_a, doc_a) != make_hash(_type_b, doc_a))
    assert(make_hash(_type_a, doc_a) == make_hash(_type_a, doc_b))
    assert(make_hash(_type_a, doc_a) != make_hash(_type_a, doc_c))


@pytest.mark.unit
def test__coersce_to_schema():
    doc = json.loads(LOGIAK_ENTITY)
    _schema_dict = json.loads(LOGIAK_SCHEMA)
    _schema = spavro.schema.parse(LOGIAK_SCHEMA)
    try:
        doc = coersce_or_fail(doc, _schema, _schema_dict)
        LOG.debug(json.dumps(doc, indent=2))
        assert(True)
    except ValueError:
        doc = coersce(doc, _schema_dict)
        result = avro_tools.AvroValidator(
            schema=_schema,
            datum=doc
        )
        LOG.debug(json.dumps(doc, indent=2))
        for error in result.errors:
            err_msg = avro_tools.format_validation_error(error)
            LOG.error(f'Validation error: {err_msg}')
