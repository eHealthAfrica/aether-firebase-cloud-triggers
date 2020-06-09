# Copyright (C) 2019 by eHealth Africa : http://www.eHealthAfrica.org
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


from collections import defaultdict
from queue import Queue, Empty
import multiprocessing as mp
from threading import Thread

from typing import Any, Dict, List

from aet.logger import get_logger

from spavro.schema import parse

from aet.kafka_utils import (
    create_topic,
    get_producer,
    get_admin_client,
    get_broker_info,
    is_kafka_available,
    produce
)

from .config import (  # noqa
    get_kafka_config,
    get_kafka_admin_config,
    get_function_config
)

from . import fb_utils  # noqa
from fb_utils import InputSet


_logger = get_logger('Manager')

MAX_KAFKA_MESSAGE_SIZE = 2_000_000

RTDB = None


class ExportManager():

    def __init__(self, source_path, cfs=None, rtdb=None):
        # set destination
        self._connect_firebase()
        self.source_path = source_path
        self.comm_pool = mp.Pool(processes=1)
        self.manager = mp.Manager()
        self.inbound = self.manager.Queue()
        self.worker_thread = Thread(target=self.worker, daemon=False)

    def _connect_firebase(self, rtdb=None, cfs=None):
        if not rtdb:
            self._init_global_firebase()
            global RTDB
            self.rtdb = RTDB
        else:
            self.rtdb = rtdb

    def _init_global_firebase(self):
        global RTDB
        if not RTDB:
            pass

    def run(self):
        _logger.info('starting')

        # Report on permanently failed submissions
        # (Failed with 400 Bad Request)
        _logger.info(f'#{fb_utils.count_quarantined(self.rtdb)} submissions in quarantine')
        self.load_failed()
        # get messages
        self.read_inbound()
        self.process()
        _logger.info('started')
        self.comm_pool.close()
        self.comm_pool.join()
        _logger.info('finished')

    def process(self):
        _logger.debug('Looking for work')
        read_subs = self.read_inbound()
        for input in read_subs.items():
            self.comm_pool.apply_async(
                func=publish,
                args=(
                    input,
                ))

    def load_failed(self) -> None:
        fb_utils.get_failed_objects(self.inbound, self.rtdb)
        fc_sub = self.processed_submissions.qsize()
        _logger.info(f'Loaded failed: {fc_sub}')

    def read_inbound(self):
        pass


def publish(input: InputSet):
    rtdb = RTDB  # GLOBAL
    # TODO look at options in InputSet and route
    return _publish_kafka(input.docs, input.schema, input.name, rtdb)


def _publish_kafka(objs: List[Any], schema: dict, _type: str, rtdb):
    try:
        _send_kafka(objs, schema, _type)
        for obj in objs:
            fb_utils.remove_from_cache(_type, obj, rtdb)
            fb_utils.remove_from_quarantine(_type, obj, rtdb)
        return len(objs)
    except RuntimeError as rte:
        _logger.info(rte)
        return _handle_kernel_errors_kafka(objs, schema, _type, rtdb)
    except Exception as no_connection:
        _logger.error(no_connection)
        fb_utils.cache_objects(_type, objs, rtdb)


def _send_kafka(objs: List[Any], schema, _type):
    # check size
    pass
    # total_size = fb_utils.utf8size(schema) + fb_utils.utf8size(objs)
    # if total_size >= MAX_KAFKA_MESSAGE_SIZE:
    #     raise RuntimeError(f'Message size: {total_size} exceeds maximum. Chunking.')
    # kadmin = get_admin_client(kafka_security)
    # if not get_broker_info(kadmin):
    #     raise ConnectionError('Could not connect to Kafka.')
    # new_topic = f'{TENANT}.logiak.{_type}'
    # create_topic(kadmin, new_topic)
    # producer = get_producer(kafka_security)
    # schema = parse(json.dumps(schema))
    # res = produce(objs, schema, new_topic, producer)


def _handle_kernel_errors_kafka(objs: List[Any], schema, _type, rtdb=None):
    _size = len(objs)
    if _size > 1:
        # break down big failures and retry parts
        # reducing by half each time
        _chunks = fb_utils.halve_iterable(objs)
        _logger.debug(f'Trying smaller chunks than {_size}...')
        return sum([_publish_kafka(chunk, schema, _type, rtdb) for chunk in _chunks])

    # Move bad object from cache to quarantine
    for obj in objs:
        fb_utils.remove_from_cache(_type, obj, rtdb)
    fb_utils.quarantine(_type, objs, rtdb)
    return 0
