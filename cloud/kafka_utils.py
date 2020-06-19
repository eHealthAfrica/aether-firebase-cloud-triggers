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

import io
from typing import Any, Dict, List, Tuple


from spavro.schema import parse
from spavro.datafile import DataFileReader
from spavro.io import DatumReader

from aet.logger import get_logger
from aet.kafka_utils import (
    create_topic,
    get_producer,
    get_admin_client,
    get_broker_info,
    produce
)

from .config import (
    get_function_config,
    get_kafka_admin_config
)
from . import fb_utils


CONF = get_function_config()
MAX_KAFKA_MESSAGE_SIZE = int(
    CONF.get('MAX_KAFKA_MESSAGE_SIZE', 100_000))  # keep things reasonably sized, MAX is 2mb

KAFKA_SECURITY = get_kafka_admin_config()
KADMIN = get_admin_client(KAFKA_SECURITY)
PRODUCER = get_producer(KAFKA_SECURITY)
_logger = get_logger('KAFKA')


def publish(
    objs: List[Tuple[str, Any]],
    schema: Dict,
    _type: str,
    rtdb=None,
    max_size=MAX_KAFKA_MESSAGE_SIZE
):
    _prepare_kafka(_type)
    # have to split out _publish because it can be called on failure and
    # we only want to try to create the topic once
    res = _publish_kafka(
        [i for (_id, i) in objs],  # strip out _ids, must be in the doc at this point
        schema, _type, rtdb, max_size
    )
    # make sure ALL callbacks have returned before moving on...
    PRODUCER.flush(timeout=20)
    return res


def _prepare_kafka(_type: str):
    TENANT = CONF.get('tenant')
    topic = fb_utils.sanitize_topic(f'{TENANT}.logiak.{_type}')
    meta = KADMIN.list_topics(timeout=3)
    if topic in meta.topics.keys():
        return
    create_topic(KADMIN, topic)
    for x in range(5):
        meta = KADMIN.list_topics(timeout=3)
        if meta:
            if topic in meta.topics.keys():
                break


def _publish_kafka(
    objs: List[Any],
    schema: Dict,
    _type: str,
    rtdb=None,
    max_size=MAX_KAFKA_MESSAGE_SIZE
) -> int:
    try:
        _callback = make_kafka_callback(rtdb, _type)
        _send_kafka(objs, schema, _type, max_size, _callback)
        return len(objs)
    except RuntimeError as rte:
        _logger.info(rte)
        return _handle_kafka_errors(objs, schema, _type, rtdb, max_size, _callback)
    except ConnectionError as no_connection:
        _logger.error(no_connection)


def make_kafka_callback(rtdb, _type):

    def _kafka_callback(err=None, msg=None, _=None, **kwargs):
        if err:
            _logger.warn('ERROR %s', [err, msg, kwargs])
        with io.BytesIO() as obj:
            obj.write(msg.value())
            reader = DataFileReader(obj, DatumReader())
            for message in reader:
                _id = message.get('id')
                if err:
                    _logger.error(f'NO-SAVE: {_type}:{_id}| err {err.name()}')
                else:
                    _logger.debug(f'SAVE: {_type}:{_id}')
                    fb_utils.remove_from_cache(_type, message, rtdb)
                    fb_utils.remove_from_quarantine(_type, message, rtdb)

    return _kafka_callback


def _send_kafka(objs: List[Any], schema, _type, max_size=MAX_KAFKA_MESSAGE_SIZE, callback=None):
    # check size
    total_size = fb_utils.utf8size(schema) + fb_utils.utf8size(objs)
    _logger.debug(f'Sending {len(objs)} of {_type} to kafka @ size {total_size}')
    if total_size >= max_size:
        raise RuntimeError(f'Message size: {total_size} exceeds maximum: {max_size}. Chunking.')
    if not get_broker_info(KADMIN):
        raise ConnectionError('Could not connect to Kafka.')
    schema = parse(schema)
    TENANT = CONF.get('tenant')
    topic = fb_utils.sanitize_topic(f'{TENANT}.logiak.{_type}')
    produce(objs, schema, topic, PRODUCER, callback=callback)
    return


def _handle_kafka_errors(
    objs: List[Any],
    schema,
    _type,
    rtdb=None,
    max_size=MAX_KAFKA_MESSAGE_SIZE,
    _callback=None
):
    _size = len(objs)
    if _size > 1:
        # break down big failures and retry parts
        # reducing by half each time
        _chunks = fb_utils.halve_iterable(objs)
        _logger.info(f'Trying smaller chunks than {_size}...')
        return sum(
            [_publish_kafka(
                chunk,
                schema,
                _type,
                rtdb,
                max_size
            ) for chunk in _chunks]
        )

    # Move bad object from cache to quarantine
    objs = [(i.get('id'), i) for i in objs]
    fb_utils.quarantine(_type, objs, rtdb)
    for _id, obj in objs:
        fb_utils.remove_from_cache(_type, obj, rtdb)

    return 0
