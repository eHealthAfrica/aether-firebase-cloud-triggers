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

import pytest

from .fixtures import *  # noqa
# from .aether_functions import *  # noqa
from .app.fb_utils import halve_iterable


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
