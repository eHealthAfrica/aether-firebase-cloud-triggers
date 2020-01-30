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

from enum import Enum
from dataclasses import dataclass, field
import pytest
from typing import Tuple
from uuid import uuid4


resource_path = '/ref/entities/'

# event_types


class DatabaseType(Enum):
    CFS = 0
    RTDB = 1


class EventType(Enum):
    WRITE = 0
    CREATE = 1
    UPDATE = 2
    DELETE = 3


EVENTS = {
    DatabaseType.RTDB: {

        EventType.WRITE: 'providers/google.firebase.database/eventTypes/ref.write',
        EventType.CREATE: 'providers/google.firebase.database/eventTypes/ref.create',
        EventType.UPDATE: 'providers/google.firebase.database/eventTypes/ref.update',
        EventType.DELETE: 'providers/google.firebase.database/eventTypes/ref.delete'
    },
    DatabaseType.CFS: {
        EventType.WRITE: 'providers/cloud.firestore/eventTypes/document.write',
        EventType.CREATE: 'providers/cloud.firestore/eventTypes/document.create',
        EventType.UPDATE: 'providers/cloud.firestore/eventTypes/document.update',
        EventType.DELETE: 'providers/cloud.firestore/eventTypes/document.delete'
    }
}


def event_from_type(db: DatabaseType, evt: EventType):
    return EVENTS[db][evt]


def info_from_event(descriptor: str) -> Tuple[DatabaseType, EventType]:
    for _type in EVENTS.keys():
        for _key, query in EVENTS[_type].items():
            if descriptor == query:
                return tuple([_type, _key])


@dataclass
class Entity:
    _id: str = field(init=False)
    _type: str
    payload: dict

    def __post_init__(self):
        self._id = self.payload.get('id')


@pytest.fixture(scope='function')
def simple_entity():
    def generator(count):
        for x in range(count):
            yield Entity('simple', {
                'id': str(uuid4()),
                'body': str(uuid4())
            })
    return generator


@pytest.fixture(scope='session')
def simple_payload():
    return {'context': {}, 'data': {}}


def contextualize(e: Entity, event: EventType, db: DatabaseType):
    descriptor = event_from_type(db, event)

    json = {
        "context": {
            "eventId": e._id,
            "timestamp": "some-timestamp",
            "eventType": descriptor,
            "resource": f'{resource_path}{e._type}/{e._id}',
        },
        "data": e.payload,
    }
    return json
