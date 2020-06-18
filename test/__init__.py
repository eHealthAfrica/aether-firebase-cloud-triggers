#!/usr/bin/env python

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


# import json
import pytest
import os
import json
from time import sleep
from uuid import uuid4
# from unittest.mock import patch

import firebase_admin
import firebase_admin.credentials
from firebase_admin.credentials import ApplicationDefault
# from firebase_admin.db import reference as RTDB
from firebase_admin.exceptions import UnavailableError
from google.api_core.exceptions import Unknown as UnknownError
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1.client import Client as CFS

# from spavro.schema import parse

from aet.kafka_utils import (
    delete_topic,
    get_admin_client
)

from aet.kafka import (
    KafkaConsumer
)

from aet.helpers import chunk_iterable
from aet.logger import get_logger
# from aet.jsonpath import CachedParser

from aether.python.avro import generation

from .app.cloud import config
from .app.cloud import fb_utils

LOG = get_logger('FIXTURE')

KAFKA_SECURITY = config.get_kafka_admin_config()
KADMIN = get_admin_client(KAFKA_SECURITY)
CONF = config.get_function_config()
TENANT = CONF.get('tenant')

URL = 'http://localhost:9013'
kafka_server = "kafka-test:29099"

TEST_DOC_COUNT = 100

project_name_rtdb = 'tenant:rtdb_test_app'
project_name_cfs = 'cfstestapp'  # NO UNDERSCORES ALLOWED!
rtdb_local = os.environ.get('FIREBASE_DATABASE_EMULATOR_HOST')
rtdb_name = 'testdb'
rtdb_url = f'http://{rtdb_local}/'
rtdb_ns = f'?ns={rtdb_name}'
rtdb_fq = rtdb_url + rtdb_ns
_rtdb_options = {
    'databaseURL': rtdb_fq,
    'projectID': project_name_rtdb
}
LOG.info(rtdb_fq)


# pick a random tenant for each run so we don't need to wipe ES.
TEST_TOPIC = 'firebase_test_topic'

GENERATED_SAMPLES = {}
# We don't want to initiate this more than once...
FIREBASE_APP = None


def get_firebase_app():
    global FIREBASE_APP
    if not FIREBASE_APP:
        FIREBASE_APP = firebase_admin.initialize_app(
            name=project_name_rtdb,
            credential=ApplicationDefault(),
            options=_rtdb_options
        )
    return FIREBASE_APP


@pytest.fixture(scope='session')
def rtdb_options():
    yield _rtdb_options


@pytest.fixture(scope='session')
def fb_app(rtdb_options):
    yield get_firebase_app()


@pytest.fixture(scope='session')
def rtdb(fb_app):
    yield fb_utils.RTDB(fb_app)


@pytest.fixture(scope='session')
def cfs():
    instance = CFS(project_name_cfs, credentials=AnonymousCredentials())
    return fb_utils.Firestore(instance=instance)


@pytest.fixture(scope='function')
def consumer():
    consumer_settings = {
        **KAFKA_SECURITY,
        **{'group.id': f'{TENANT}.logiak-test-{uuid4()}'},
        **{
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True,
            # 'auto.commit.interval.ms': 2500,
            'aether_emit_flag_required': False,
            'aether_masking_schema_levels': ['false', 'true'],
            'aether_masking_schema_emit_level': 'false',
            # 'heartbeat.interval.ms': 2500,
            # 'session.timeout.ms': 18000,
            # 'request.timeout.ms': 20000
        }
    }
    _consumer = KafkaConsumer(**consumer_settings)
    yield _consumer
    _consumer.close()


@pytest.mark.integration
@pytest.fixture(scope='function')
def load_cache(rtdb, sample_generator):

    def load(_type, count=TEST_DOC_COUNT):
        base_path = 'test_project'
        _db = fb_utils.RTDBTarget(base_path=base_path, rtdb=rtdb)
        _schema = ANNOTATED_SCHEMA
        docs_path = f'{fb_utils._SYNC_QUEUE}/{_type}/documents/'
        schema_path = f'{base_path}/{fb_utils._SYNC_QUEUE}/{_type}/schema'
        options_path = f'{base_path}/{fb_utils._SYNC_QUEUE}/{_type}/options'
        # using raw ref you have to dumps yourself
        _db._raw_reference(schema_path).set(json.dumps(_schema))
        _db._raw_reference(options_path).set(json.dumps({}))
        for subset in sample_generator(max=count, chunk=count):
            for _doc in subset:
                _id = _doc['id']
                _db.add(_id, docs_path, _doc)
    yield load


def get_local_session(self):
    if self.app:
        return self.app
    self.app = get_firebase_app()
    self.get_rtdb()
    self.get_cloud_firestore()
    return self.app


# def get_local_cfs(self):
#     return CFS(project_name_cfs, credentials=AnonymousCredentials())


# # @pytest.mark.integration
# @pytest.fixture(scope='session', autouse=True)
# def create_remote_kafka_assets(request, sample_generator, *args):
#     # @mark annotation does not work with autouse=True.
#     if 'integration' not in request.config.invocation_params.args:
#         LOG.debug(f'NOT creating Kafka Assets')
#         yield None
#     else:
#         LOG.debug(f'Creating Kafka Assets')
#         kafka_security = config.get_kafka_admin_config()
#         kadmin = get_admin_client(kafka_security)
#         new_topic = f'{TENANT}.{TEST_TOPIC}'
#         create_topic(kadmin, new_topic)
#         GENERATED_SAMPLES[new_topic] = []
#         producer = get_producer(kafka_security)
#         schema = parse(json.dumps(ANNOTATED_SCHEMA))
#         for subset in sample_generator(max=100, chunk=10):
#             GENERATED_SAMPLES[new_topic].extend(subset)
#             res = produce(subset, schema, new_topic, producer)
#             LOG.debug(res)
#         yield None  # end of work before clean-up
#         LOG.debug(f'deleting topic: {new_topic}')
#         delete_topic(kadmin, new_topic)


# raises UnavailableError
def check_app_alive(rtdb, cfs):
    ref = rtdb.reference('some/path')
    cref = cfs.ref('test2', 'adoc')
    # cref = cfs.collection(u'test2').document(u'adoc')
    return (ref and cref)


@pytest.fixture(scope='session', autouse=True)
def check_local_firebase_readyness(request, rtdb, cfs, *args):
    # @mark annotation does not work with autouse=True
    # if 'integration' not in request.config.invocation_params.args:
    #     LOG.debug(f'NOT Checking for LocalFirebase')
    #     return
    LOG.debug('Waiting for Firebase')
    for x in range(30):
        try:
            check_app_alive(rtdb, cfs)
            LOG.debug(f'Firebase ready after {x} seconds')
            return
        except (UnavailableError, UnknownError):
            sleep(1)

    raise TimeoutError('Could not connect to Firebase for integration test')


@pytest.mark.unit
@pytest.mark.integration
@pytest.fixture(scope='session')
def sample_generator():
    t = generation.SampleGenerator(ANNOTATED_SCHEMA)
    t.set_overrides('geometry.latitude', {'min': 44.754512, 'max': 53.048971})
    t.set_overrides('geometry.longitude', {'min': 8.013135, 'max': 28.456375})
    t.set_overrides('url', {'constant': 'http://ehealthafrica.org'})
    for field in ['beds', 'staff_doctors', 'staff_nurses']:
        t.set_overrides(field, {'min': 0, 'max': 50})

    def _gen(max=None, chunk=None):

        def _single(max):
            if not max:
                while True:
                    yield t.make_sample()
            for x in range(max):
                yield t.make_sample()

        def _chunked(max, chunk):
            return chunk_iterable(_single(max), chunk)

        if chunk:
            yield from _chunked(max, chunk)
        else:
            yield from _single(max)
    yield _gen


ANNOTATED_SCHEMA = {
    'doc': 'MySurvey (title: HS OSM Gather Test id: gth_hs_test, version: 2)',
    'name': 'MySurvey',
    'type': 'record',
    'fields': [
        {
            'doc': 'xForm ID',
            'name': '_id',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey'
        },
        {
            'doc': 'xForm version',
            'name': '_version',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_default_visualization': 'undefined'
        },
        {
            'doc': 'Surveyor',
            'name': '_surveyor',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey'
        },
        {
            'doc': 'Submitted at',
            'name': '_submitted_at',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'dateTime'
        },
        {
            'name': '_start',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'dateTime'
        },
        {
            'name': 'timestamp',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'dateTime'
        },
        {
            'name': 'username',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'name': 'source',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'name': 'osm_id',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Name of Facility',
            'name': 'name',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Address',
            'name': 'addr_full',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Phone Number',
            'name': 'contact_number',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Facility Operator Name',
            'name': 'operator',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Operator Type',
            'name': 'operator_type',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_default_visualization': 'pie',
            '@aether_lookup': [
                {
                    'label': 'Public',
                    'value': 'public'
                },
                {
                    'label': 'Private',
                    'value': 'private'
                },
                {
                    'label': 'Community',
                    'value': 'community'
                },
                {
                    'label': 'Religious',
                    'value': 'religious'
                },
                {
                    'label': 'Government',
                    'value': 'government'
                },
                {
                    'label': 'NGO',
                    'value': 'ngo'
                },
                {
                    'label': 'Combination',
                    'value': 'combination'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'Facility Location',
            'name': 'geometry',
            'type': [
                'null',
                {
                    'doc': 'Facility Location',
                    'name': 'geometry',
                    'type': 'record',
                    'fields': [
                        {
                            'doc': 'latitude',
                            'name': 'latitude',
                            'type': [
                                'null',
                                'float'
                            ],
                            'namespace': 'MySurvey.geometry'
                        },
                        {
                            'doc': 'longitude',
                            'name': 'longitude',
                            'type': [
                                'null',
                                'float'
                            ],
                            'namespace': 'MySurvey.geometry'
                        },
                        {
                            'doc': 'altitude',
                            'name': 'altitude',
                            'type': [
                                'null',
                                'float'
                            ],
                            'namespace': 'MySurvey.geometry'
                        },
                        {
                            'doc': 'accuracy',
                            'name': 'accuracy',
                            'type': [
                                'null',
                                'float'
                            ],
                            'namespace': 'MySurvey.geometry'
                        }
                    ],
                    'namespace': 'MySurvey',
                    '@aether_extended_type': 'geopoint'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'geopoint'
        },
        {
            'doc': 'Operational Status',
            'name': 'operational_status',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_default_visualization': 'pie',
            '@aether_lookup': [
                {
                    'label': 'Operational',
                    'value': 'operational'
                },
                {
                    'label': 'Non Operational',
                    'value': 'non_operational'
                },
                {
                    'label': 'Unknown',
                    'value': 'unknown'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'When is the facility open?',
            'name': '_opening_hours_type',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Pick the days of the week open and enter hours for each day',
                    'value': 'oh_select'
                },
                {
                    'label': 'Only open on weekdays with the same hours every day.',
                    'value': 'oh_weekday'
                },
                {
                    'label': '24/7 - All day, every day',
                    'value': 'oh_24_7'
                },
                {
                    'label': 'Type in OSM String by hand (Advanced Option)',
                    'value': 'oh_advanced'
                },
                {
                    'label': 'I do not know the operating hours',
                    'value': 'oh_unknown'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'Which days is this facility open?',
            'name': '_open_days',
            'type': [
                'null',
                {
                    'type': 'array',
                    'items': 'string'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Monday',
                    'value': 'Mo'
                },
                {
                    'label': 'Tuesday',
                    'value': 'Tu'
                },
                {
                    'label': 'Wednesday',
                    'value': 'We'
                },
                {
                    'label': 'Thursday',
                    'value': 'Th'
                },
                {
                    'label': 'Friday',
                    'value': 'Fr'
                },
                {
                    'label': 'Saturday',
                    'value': 'Sa'
                },
                {
                    'label': 'Sunday',
                    'value': 'Su'
                },
                {
                    'label': 'Public Holidays',
                    'value': 'PH'
                }
            ],
            '@aether_extended_type': 'select'
        },
        {
            'doc': 'Open hours by day of the week',
            'name': '_dow_group',
            'type': [
                'null',
                {
                    'doc': 'Open hours by day of the week',
                    'name': '_dow_group',
                    'type': 'record',
                    'fields': [
                        {
                            'doc': 'Enter open hours for each day:',
                            'name': '_hours_note',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Monday open hours',
                            'name': '_mon_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Tuesday open hours',
                            'name': '_tue_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Wednesday open hours',
                            'name': '_wed_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Thursday open hours',
                            'name': '_thu_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Friday open hours',
                            'name': '_fri_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Saturday open hours',
                            'name': '_sat_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Sunday open hours',
                            'name': '_sun_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'doc': 'Public Holiday open hours',
                            'name': '_ph_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        },
                        {
                            'name': '_select_hours',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey._dow_group',
                            '@aether_extended_type': 'string'
                        }
                    ],
                    'namespace': 'MySurvey',
                    '@aether_extended_type': 'group'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'group'
        },
        {
            'doc': 'Enter weekday hours',
            'name': '_weekday_hours',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'OSM:opening_hours',
            'name': '_advanced_hours',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'name': 'opening_hours',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Verify the open hours are correct or go back and fix:',
            'name': '_disp_hours',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'Facility Category',
            'name': 'amenity',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Clinic',
                    'value': 'clinic'
                },
                {
                    'label': 'Doctors',
                    'value': 'doctors'
                },
                {
                    'label': 'Hospital',
                    'value': 'hospital'
                },
                {
                    'label': 'Dentist',
                    'value': 'dentist'
                },
                {
                    'label': 'Pharmacy',
                    'value': 'pharmacy'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'Available Services',
            'name': 'healthcare',
            'type': [
                'null',
                {
                    'type': 'array',
                    'items': 'string'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Doctor',
                    'value': 'doctor'
                },
                {
                    'label': 'Pharmacy',
                    'value': 'pharmacy'
                },
                {
                    'label': 'Hospital',
                    'value': 'hospital'
                },
                {
                    'label': 'Clinic',
                    'value': 'clinic'
                },
                {
                    'label': 'Dentist',
                    'value': 'dentist'
                },
                {
                    'label': 'Physiotherapist',
                    'value': 'physiotherapist'
                },
                {
                    'label': 'Alternative',
                    'value': 'alternative'
                },
                {
                    'label': 'Laboratory',
                    'value': 'laboratory'
                },
                {
                    'label': 'Optometrist',
                    'value': 'optometrist'
                },
                {
                    'label': 'Rehabilitation',
                    'value': 'rehabilitation'
                },
                {
                    'label': 'Blood donation',
                    'value': 'blood_donation'
                },
                {
                    'label': 'Birthing center',
                    'value': 'birthing_center'
                }
            ],
            '@aether_extended_type': 'select'
        },
        {
            'doc': 'Specialities',
            'name': 'speciality',
            'type': [
                'null',
                {
                    'type': 'array',
                    'items': 'string'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'xx',
                    'value': 'xx'
                }
            ],
            '@aether_extended_type': 'select'
        },
        {
            'doc': 'Speciality medical equipment available',
            'name': 'health_amenity_type',
            'type': [
                'null',
                {
                    'type': 'array',
                    'items': 'string'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Ultrasound',
                    'value': 'ultrasound'
                },
                {
                    'label': 'MRI',
                    'value': 'mri'
                },
                {
                    'label': 'X-Ray',
                    'value': 'x_ray'
                },
                {
                    'label': 'Dialysis',
                    'value': 'dialysis'
                },
                {
                    'label': 'Operating Theater',
                    'value': 'operating_theater'
                },
                {
                    'label': 'Laboratory',
                    'value': 'laboratory'
                },
                {
                    'label': 'Imaging Equipment',
                    'value': 'imaging_equipment'
                },
                {
                    'label': 'Intensive Care Unit',
                    'value': 'intensive_care_unit'
                },
                {
                    'label': 'Emergency Department',
                    'value': 'emergency_department'
                }
            ],
            '@aether_extended_type': 'select'
        },
        {
            'doc': 'Does this facility provide Emergency Services?',
            'name': 'emergency',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Yes',
                    'value': 'yes'
                },
                {
                    'label': 'No',
                    'value': 'no'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'Does the pharmacy dispense prescription medication?',
            'name': 'dispensing',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Yes',
                    'value': 'yes'
                },
                {
                    'label': 'No',
                    'value': 'no'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'Number of Beds',
            'name': 'beds',
            'type': [
                'null',
                'int'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'int',
            '@aether_masking': 'private'
        },
        {
            'doc': 'Number of Doctors',
            'name': 'staff_doctors',
            'type': [
                'null',
                'int'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'int',
            '@aether_masking': 'private'
        },
        {
            'doc': 'Number of Nurses',
            'name': 'staff_nurses',
            'type': [
                'null',
                'int'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'int',
            '@aether_masking': 'private'
        },
        {
            'doc': 'Types of insurance accepted?',
            'name': 'insurance',
            'type': [
                'null',
                {
                    'type': 'array',
                    'items': 'string'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Public',
                    'value': 'public'
                },
                {
                    'label': 'Private',
                    'value': 'private'
                },
                {
                    'label': 'None',
                    'value': 'no'
                },
                {
                    'label': 'Unknown',
                    'value': 'unknown'
                }
            ],
            '@aether_extended_type': 'select',
            '@aether_masking': 'public'
        },
        {
            'doc': 'Is this facility wheelchair accessible?',
            'name': 'wheelchair',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Yes',
                    'value': 'yes'
                },
                {
                    'label': 'No',
                    'value': 'no'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'What is the source of water for this facility?',
            'name': 'water_source',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Well',
                    'value': 'well'
                },
                {
                    'label': 'Water works',
                    'value': 'water_works'
                },
                {
                    'label': 'Manual pump',
                    'value': 'manual_pump'
                },
                {
                    'label': 'Powered pump',
                    'value': 'powered_pump'
                },
                {
                    'label': 'Groundwater',
                    'value': 'groundwater'
                },
                {
                    'label': 'Rain',
                    'value': 'rain'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'What is the source of power for this facility?',
            'name': 'electricity',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_lookup': [
                {
                    'label': 'Power grid',
                    'value': 'grid'
                },
                {
                    'label': 'Generator',
                    'value': 'generator'
                },
                {
                    'label': 'Solar',
                    'value': 'solar'
                },
                {
                    'label': 'Other Power',
                    'value': 'other'
                },
                {
                    'label': 'No Power',
                    'value': 'none'
                }
            ],
            '@aether_extended_type': 'select1'
        },
        {
            'doc': 'URL for this location (if available)',
            'name': 'url',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'In which health are is the facility located?',
            'name': 'is_in_health_area',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'doc': 'In which health zone is the facility located?',
            'name': 'is_in_health_zone',
            'type': [
                'null',
                'string'
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'string'
        },
        {
            'name': 'meta',
            'type': [
                'null',
                {
                    'name': 'meta',
                    'type': 'record',
                    'fields': [
                        {
                            'name': 'instanceID',
                            'type': [
                                'null',
                                'string'
                            ],
                            'namespace': 'MySurvey.meta',
                            '@aether_extended_type': 'string'
                        }
                    ],
                    'namespace': 'MySurvey',
                    '@aether_extended_type': 'group'
                }
            ],
            'namespace': 'MySurvey',
            '@aether_extended_type': 'group'
        },
        {
            'doc': 'UUID',
            'name': 'id',
            'type': 'string'
        }
    ],
    'namespace': 'org.ehealthafrica.aether.odk.xforms.Mysurvey'
}

LOGIAK_SCHEMA = '''
{
  "name": "patient",
  "type": "record",
  "@logiak": {
    "uuid": "032ba674-ebea-4c64-9161-3de0362aef0c"
  },
  "fields": [
    {
      "name": "ci_status",
      "description": "ci_status",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "24e7bfa2-b251-4ce4-a492-e4edca2198de",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "completion_status",
      "description": "completion_status",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "0761f166-435e-4c7f-ad87-b7e926205696",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "completion_status_no_reason",
      "description": "",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "1a73ddd9-2089-4f3c-a20d-93e352284e99",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "complication_ards",
      "description": "acute respiratory distress syndrome (ards)",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "6e08cb23-a0bf-4d2a-9cd3-f14a43a26791",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_emo",
      "description": "extracorporeal membrane oxygenation required (emo)",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "434fe02c-20f1-4bc2-ae54-9edfd6885fcb",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_hospital_name",
      "description": "name of the hospital",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "69dbf128-7b15-4710-ad75-29c2068e3afa",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "complication_hospitalisation",
      "description": "hospitalization required",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "18c2c01a-8b1e-41e9-9d5d-185bdd8e1d2d",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_icu",
      "description": "intensive care unit (icu) admission required",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "48705f2a-724b-4b1d-8c39-b144e270ff48",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_mec_vent",
      "description": "mechanical ventilation required",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "5f8d70d6-ed66-4ccd-b35d-3671929acd23",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_other_illness",
      "description": "other severe or life-threatening illness suggestive of an infection",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "3ac5a0f9-9b06-45da-a47a-b4a7fc0868d1",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_other_illness_other",
      "description": "other illness",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "c2d3cda6-e12e-4b97-85b8-3e076c0eedde",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "complication_xray",
      "description": "pneumonia chest x-ray",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "dc291ee8-349a-49a4-8c8a-aaf4ad0ab2ea",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "complication_xray_date",
      "description": "x-ray date",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "351be457-bbac-46bd-b295-23cd035aa511",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "created",
      "description": "created",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "e884b30b-0bad-4505-af2c-2010ce386d30",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "data_collector_email",
      "description": "email",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "80bfbb47-c2d1-49c1-8070-a4822a8ab36f",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "data_collector_hf",
      "description": "data collector health facility",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "03eb21ca-dd5d-4977-ae8b-e98b908bab14",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "data_collector_institution",
      "description": "data collector institution",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "69e0e204-9656-4472-b0d8-6768527f9e2e",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "data_collector_name",
      "description": "name of data collector",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "3d9a534a-6c24-42c0-8560-33b9f674c089",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "data_collector_phone",
      "description": "data collector phone number",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "bc5cb98f-95f1-457f-8ba6-52b78147f589",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "email",
      "description": "email",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "5be4a9f4-4937-4c69-a8cb-acf3a972c8b1",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "exposure_contact",
      "description": "exposure_contact",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "b66eb8a1-8e13-4d1c-8a65-af96bb3e3b4e",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_contact_last_date",
      "description": "exposure_contact_last_date",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "16dfb352-7804-4b13-8853-5a20af725f81",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "exposure_domestic_travel",
      "description": "exposure_domestic_travel",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "10ac4549-52ba-4b77-a12e-eb343db485a4",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_domestic_travel_city",
      "description": "exposure_domestic_travel_city",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "d5ec6a13-e021-47c6-b0c9-784977ff2f42",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_domestic_travel_date_from",
      "description": "exposure_domestic_travel_date_from",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "262cf243-411b-4196-8907-13adea154ae4",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "exposure_domestic_travel_date_to",
      "description": "exposure_domestic_travel_date_to",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "8eb3242c-d770-408f-a0b9-0fa2330936e5",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "exposure_domestic_travel_region",
      "description": "exposure_domestic_travel_region",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "357e196a-5dfb-4229-85a5-cf54a479a344",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_inpatient_visit",
      "description": "exposure_inpatient_visit",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "8b0e7fd5-25a0-4344-9619-59ab565e0a2c",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_international_travel",
      "description": "exposure_international_travel",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "52d7b305-c348-4eb9-9324-d1dc284cd93f",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_international_travel_cities",
      "description": "exposure_international_travel_cities",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "5c464300-88cd-4e81-9bb7-3d3a58d183f4",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_international_travel_countries",
      "description": "exposure_international_travel_countries",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "aa164312-86b0-4605-8037-447f5c83e203",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_international_travel_date_from",
      "description": "exposure_international_travel_date_from",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "e20a1e19-c070-4422-ba82-3674d0ef06e4",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "exposure_international_travel_date_to",
      "description": "exposure_international_travel_date_to",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "628c8e13-357e-4c13-8aa3-4b084744dc24",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "exposure_location",
      "description": "exposure_location",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "772b40b7-a6a1-4088-a1c2-e5884b45d173",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_mass_gathering",
      "description": "exposure_mass_gathering",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "a50c9af6-c0a1-4833-b681-403247e54e49",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_mass_gathering_specify",
      "description": "exposure_mass_gathering_specify",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "90dc66ea-5f77-43a3-b407-63a754a1b260",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_outpatient_visit",
      "description": "exposure_outpatient_visit",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "874ca0fc-50a7-4860-8fa9-4355ea9f9ef2",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_patient_occupation",
      "description": "exposure_patient_occupation",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "54a0662c-76c6-4228-ab33-82995e80856d",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_patient_occupation_location",
      "description": "exposure_patient_occupation_location",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "0b098154-26d2-41f4-b884-509d06b7a8d4",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "exposure_similar_illness",
      "description": "exposure_similar_illness",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "34068938-ccb7-41a5-9d5b-841399f88b2a",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "exposure_traditional",
      "description": "exposure_traditional",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "cc4e0836-5c44-45e1-ac3a-2ade62ecb79f",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "firebase_uuid",
      "description": "firebase_uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "f686c9bd-38d9-4138-ac8c-541c2fbd2d3c",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "group_uuid",
      "description": "group_uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "93c633f2-0f94-468f-b7fa-24641afe0df5",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "isolation_status_patient_isolated",
      "description": "isolation_status_patient_isolated",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "137e1597-7b51-4a97-8965-ea0f3f2d5401",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "isolation_status_patient_isolated_address",
      "description": "isolation_status_patient_isolated_address",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "a6532614-8500-4ff0-9bd7-f0ec62d95f8f",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "isolation_status_patient_isolated_date_from",
      "description": "isolation_status_patient_isolated_date_from",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "2700bfbd-f5d7-4e9f-9e7f-5f763cc76e52",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "isolation_status_patient_isolated_date_to",
      "description": "isolation_status_patient_isolated_date_to",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "c94b4c11-a5aa-4922-8556-396b6e9618e8",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "isolation_status_patient_isolated_location",
      "description": "isolation_status_patient_isolated_location",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "4d941e11-84ff-446d-b62a-322cb9d0e66b",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_code",
      "description": "lab_code",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "3567c877-b15c-4866-8cac-0d9ef8f7db2e",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_name",
      "description": "lab_name",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "4a9fb9c9-4cc8-4034-9ceb-2a5531a6d0c0",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_note",
      "description": "lab_note",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "47bd323c-1c91-48f3-95d4-10646afdc063",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_scientist_id",
      "description": "lab_scientist_id",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "8e7d8660-321b-4018-b8cb-46a6844b954e",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_scientist_name",
      "description": "lab_scientist_name",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "24ec852d-21a8-4eec-8368-4a1aa153d802",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "lab_test_completion_date",
      "description": "lab_test_completion_date",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "bcb33dd6-d36d-40ad-b039-90f46dc4e3fa",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "latitude",
      "description": "latitude",
      "type": [
        "null",
        "double"
      ],
      "decimalplaces": "0",
      "@logiak": {
        "uuid": "2ae13896-f800-4dd0-bdbd-6122f8d4afa6",
        "type": "number",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "defaultvalue": "0.0",
        "tags": ""
      }
    },
    {
      "name": "longitude",
      "description": "longitude",
      "type": [
        "null",
        "double"
      ],
      "decimalplaces": "0",
      "@logiak": {
        "uuid": "0753a963-ea12-43d8-9942-e84feadeb467",
        "type": "number",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "defaultvalue": "0.0",
        "tags": ""
      }
    },
    {
      "name": "managed_uuid",
      "description": "managed_uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "88e161af-ad43-40cb-bdc3-3210a303e850",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "modified",
      "description": "modified",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "8844392c-8c60-4edb-859f-b59923a6fba9",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "patient_age_month",
      "description": "age (in months)",
      "type": [
        "null",
        "double"
      ],
      "decimalplaces": "0",
      "@logiak": {
        "uuid": "16b941de-a817-444b-9824-ed3b3bc22eec",
        "type": "number",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0.0",
        "tags": ""
      }
    },
    {
      "name": "patient_age_year",
      "description": "age (in years)",
      "type": [
        "null",
        "double"
      ],
      "decimalplaces": "0",
      "@logiak": {
        "uuid": "aa9f5af6-a046-48c6-a447-37f273d4f102",
        "type": "number",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0.0",
        "tags": ""
      }
    },
    {
      "name": "patient_case_epid",
      "description": "epid/unique case id",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "75737bfa-31ee-4871-9868-bb33bd10da61",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_country_residence",
      "description": "country of residence",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2e46cbad-0183-4b72-868c-446008fe5950",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "Nigeria",
        "tags": ""
      }
    },
    {
      "name": "patient_current_status",
      "description": "current status",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "95c7d77a-c9d3-4439-ad1e-314d3c3647ac",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "patient_dob",
      "description": "date of birth",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "423ae412-858b-4af9-8d2e-c725bde7495b",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "patient_email",
      "description": "email",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "10be4f53-b855-4639-9481-a1fab97fd113",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_family_name",
      "description": "surname / family name",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "4673c252-072c-4a9c-9ddf-cc7c78620886",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_first_name",
      "description": "first name(s)",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "dec60d89-5a43-4d73-bb4b-19169ebca749",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_gender",
      "description": "gender",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "72cb722d-149c-4acf-8a24-107e65f16153",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_identifier",
      "description": "national social number/id/identifier (if applicable)",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "7cae0a27-33bc-44ce-b584-e55e07dcf364",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_is_respondent",
      "description": "is the person providing the information the patient?",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "ae55b6c5-de97-4a1e-a47c-445adba8de7f",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "patient_is_symptomatic",
      "description": "does the patient show symptoms?",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "0587d363-ceec-46b0-9086-b74bb15c73ee",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "patient_lga",
      "description": "lga",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "ad06a626-2672-48d0-8ab4-bf252248e3f3",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_phone",
      "description": "phone (mobile) number",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "6507cf3d-1f3f-4797-9053-7b22da9f1a08",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_residential_address",
      "description": "residential address",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "3b45f800-e2f9-4c5b-9210-735d15961cff",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_state",
      "description": "state",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "09fb36b9-8122-47bc-9434-4874d391e417",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_status",
      "description": "case status",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "ad7242db-d2bb-4fb1-9ccd-66eb20191b81",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_test_result",
      "description": "patient_test_result",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "0ac78d10-7334-4dd3-b827-5d077218c17c",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "patient_uuid",
      "description": "patient_uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2d661565-7efe-45b7-af82-23941de93d03",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "patient_ward",
      "description": "ward",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "058ab091-bd62-49cc-b2d8-e04efc6bee9c",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "respondent_address",
      "description": "respondent address",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2be5d37c-4319-4ee5-8483-d8958cba15b5",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "respondent_dob",
      "description": "date of birth",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "c40fe82c-f118-40a3-9c0a-663e8637f7ea",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "respondent_first_name",
      "description": "first name",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2f1d9826-2185-43e1-9b45-bccc9ac97964",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "respondent_gender",
      "description": "gender",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "096cca56-a5d8-48e5-9915-69e89dcfe42b",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "respondent_phone",
      "description": "phone (mobile) number",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "40c29dd4-8449-40e7-8452-183810151b3e",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "respondent_surname",
      "description": "surname",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "22d15833-9aff-4b80-af3c-1757806b77a0",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "role_uuid",
      "description": "role_uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "160a0000-8633-4cfc-b95d-16bbb1585f01",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_barcode",
      "description": "sample_collection_barcode",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "ff2df602-704f-4c19-bdea-8db4812fd347",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_baseline_serum_date",
      "description": "date baseline serum taken",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "665a62ac-0f8f-46ce-ac38-ae48a900b69a",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_baseline_serum_taken",
      "description": "has baseline serum been taken",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "a823e8db-757c-4e11-98fc-39ca71e4aeec",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_date",
      "description": "date respiratory sample collected",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "ff071b41-075b-4eb2-a49d-0b565b8b21d2",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_is_ready_for_collection",
      "description": "",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "b0a6f0e1-be38-4e41-889b-98b8be0cce4b",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_other_samples",
      "description": "other samples collected",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "3727460f-183a-4c9c-998a-b8188d6a067d",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_other_samples_collected",
      "description": "were other samples collected?",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "136996c1-9e02-4381-b1dd-a93276f43fc2",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_other_samples_date",
      "description": "date taken",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "7ef1b210-e75f-4f6d-a079-7a85b142391c",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "sample_collection_type",
      "description": "sample_collection_type",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "9335b3ed-554a-4e20-afa2-e83320fc9579",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "tags": ""
      }
    },
    {
      "name": "symptom_cough",
      "description": "cough",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "83b399a7-b94f-4b27-bde0-c0a9769f3e7b",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_date",
      "description": "date of first symptom onset",
      "type": [
        "null",
        "long"
      ],
      "@logiak": {
        "uuid": "e2689a2a-0e26-49c9-b508-2794823b5613",
        "type": "date",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "0",
        "tags": ""
      }
    },
    {
      "name": "symptom_diarrhea",
      "description": "diarrhrea",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2cfa0345-49c8-4199-84fe-f99618388757",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_fever",
      "description": "fever (≥ 38.0° C) or history of fever",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "2df3d607-23b4-4b20-ab1f-101ad977ce40",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_nausea",
      "description": "nausea",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "d152ece7-8703-4c7b-82a6-726b3f669162",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_runny_nose",
      "description": "runny nose",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "f4583945-d3fc-44cd-9683-e940c8c82ffa",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_shortness_breath",
      "description": "shortness of breath",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "c8a6f928-433c-498b-bc9f-a37cb2327252",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_sore_throat",
      "description": "sore throat",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "20ad7521-a184-4811-a7bd-6a37114b25de",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "symptom_vomiting",
      "description": "vomiting",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "9795c729-91a2-4892-824a-d13408517a83",
        "type": "item",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "novalue",
        "tags": ""
      }
    },
    {
      "name": "uuid",
      "description": "uuid",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "8feab5c1-c23e-4a96-8ae5-5f41294b9b99",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "version_created",
      "description": "version_created",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "774184e6-3096-4e62-8bbd-41bc515f274b",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "version_modified",
      "description": "version_modified",
      "type": [
        "null",
        "string"
      ],
      "@logiak": {
        "uuid": "f5a1d4c8-cb2f-43b7-ba82-e7a2230fcfa1",
        "type": "text",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "false",
        "tags": ""
      }
    },
    {
      "name": "workflow_case_complete",
      "description": "workflow_case_complete",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "35cf641e-2443-4dcb-9ea5-1ce76eb42d33",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "workflow_cif_needs_cas_status",
      "description": "workflow_cif_needs_cas_status",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "b9382131-d976-47a6-ab5b-05884ae37dd7",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "workflow_ready_for_sample_collection",
      "description": "workflow_ready_for_sample_collection",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "629fb79f-485e-46fa-91e3-f0bdc17d6d2e",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    },
    {
      "name": "workflow_waiting_lab_results",
      "description": "workflow_waiting_lab_results",
      "type": [
        "null",
        "boolean"
      ],
      "@logiak": {
        "uuid": "4b1f63bc-d17f-4642-8d72-a2f045e62615",
        "type": "boolean",
        "workflow": "false",
        "personal": "false",
        "unique": "false",
        "user-defined": "true",
        "defaultvalue": "false",
        "tags": ""
      }
    }
  ]
}
'''

LOGIAK_ENTITY = '''
{
  "exposure_domestic_travel_date_to": "0",
  "patient_case_epid": "she",
  "isolation_status_patient_isolated": "novalue",
  "complication_hospitalisation": "novalue",
  "completion_status": "yes",
  "complication_ards": "novalue",
  "respondent_surname": "",
  "patient_lga": "Dala",
  "workflow_case_complete": "false",
  "exposure_patient_occupation_location": "",
  "data_collector_hf": "HF-KAN-002",
  "isolation_status_patient_isolated_address": "",
  "exposure_domestic_travel": "novalue",
  "sample_collection_date": "0",
  "modified": "1592312767867",
  "complication_emo": "novalue",
  "version_created": "0.2.29",
  "exposure_domestic_travel_city": "",
  "exposure_mass_gathering": "novalue",
  "group_uuid": "0e41e39e-d6d3-4558-8e7c-1c930f65adc5",
  "sample_collection_type": "",
  "patient_country_residence": "Nigeria",
  "patient_uuid": "e7713723-ae32-4e4d-aa7b-1239160c9caf",
  "respondent_address": "",
  "patient_residential_address": "sent",
  "complication_xray": "novalue",
  "patient_identifier": "",
  "version_modified": "0.2.29",
  "apk_version_modified": "0.0.109+79",
  "firebase_uuid": "4WpFipBTgLbRJgM8FknkC8SvL9s1",
  "sample_collection_baseline_serum_date": "0",
  "created": "1592312767868",
  "sample_collection_barcode": "",
  "email": "doug.moran@ehealthnigeria.org",
  "sample_collection_other_samples_collected": "novalue",
  "exposure_traditional": "novalue",
  "data_collector_institution": "Health Facility K1",
  "symptom_cough": "novalue",
  "complication_icu": "novalue",
  "patient_family_name": "do",
  "isolation_status_patient_isolated_location": "",
  "sample_collection_is_ready_for_collection": "false",
  "isolation_status_patient_isolated_date_from": "0",
  "symptom_diarrhea": "novalue",
  "respondent_dob": "0",
  "symptom_shortness_breath": "novalue",
  "workflow_cif_needs_cas_status": "true",
  "respondent_phone": "",
  "workflow_waiting_lab_results": "false",
  "patient_state": "Kano",
  "lab_note": "",
  "respondent_gender": "novalue",
  "patient_status": "unknown",
  "patient_dob": "1592262000000",
  "symptom_sore_throat": "novalue",
  "patient_ward": "Kabuwaya",
  "patient_phone": "do",
  "complication_xray_date": "0",
  "exposure_inpatient_visit": "novalue",
  "exposure_mass_gathering_specify": "",
  "lab_scientist_id": "",
  "patient_is_respondent": "true",
  "data_collector_phone": "07726574379",
  "exposure_international_travel_countries": "",
  "exposure_patient_occupation": "",
  "apk_version_created": "0.0.109+79",
  "patient_age_year": "0.0",
  "symptom_vomiting": "novalue",
  "exposure_domestic_travel_region": "",
  "uuid": "7e45d739-7619-49ad-9082-255026ea6385",
  "symptom_runny_nose": "novalue",
  "patient_email": "do",
  "patient_current_status": "alive",
  "exposure_contact_last_date": "0",
  "exposure_similar_illness": "novalue",
  "complication_hospital_name": "",
  "workflow_ready_for_sample_collection": "false",
  "data_collector_email": "cm@k1.ng",
  "patient_age_month": "0.0",
  "exposure_location": "",
  "isolation_status_patient_isolated_date_to": "0",
  "complication_other_illness_other": "",
  "exposure_international_travel_date_to": "0",
  "lab_code": "",
  "exposure_outpatient_visit": "novalue",
  "symptom_date": "0",
  "exposure_international_travel_cities": "",
  "latitude": "9.0705809",
  "data_collector_name": "Chukwu Mobolaji",
  "patient_first_name": "XXXXX",
  "completion_status_no_reason": "",
  "sample_collection_baseline_serum_taken": "novalue",
  "exposure_contact": "novalue",
  "patient_gender": "male",
  "sample_collection_other_samples_date": "0",
  "exposure_international_travel": "novalue",
  "complication_mec_vent": "novalue",
  "respondent_first_name": "",
  "ci_status": "CIF Needs Case Status",
  "sample_collection_other_samples": "",
  "symptom_fever": "novalue",
  "patient_is_symptomatic": "false",
  "slot": null,
  "lab_name": "",
  "lab_scientist_name": "",
  "patient_test_result": "novalue",
  "role_uuid": "fc1600a8-2e07-42d6-b54b-22cf1bde4d79",
  "complication_other_illness": "novalue",
  "exposure_international_travel_date_from": "0",
  "symptom_nausea": "novalue",
  "longitude": "7.4136409",
  "managed_uuid": "b7113a86-8df7-485b-ac7f-1c3fff9e5433",
  "exposure_domestic_travel_date_from": "0",
  "lab_test_completion_date": "0"
}
'''
