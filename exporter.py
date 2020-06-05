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

from . import fb_utils  # noqa


_logger = get_logger('Manager')


CFS = None
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
        if not cfs:
            self._init_global_firebase()
            global CFS
            self.cfs = CFS
        else:
            self.cfs = cfs
        if not rtdb:
            self._init_global_firebase()
            global RTDB
            self.rtdb = RTDB
        else:
            self.rtdb = rtdb

    def _init_global_firebase(self):
        global CFS
        if not CFS:
            pass
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
        self.comm_pool.close()
        self.comm_pool.join()
        _logger.info('started')

    def process(self):
        _logger.debug('Looking for work')
        read_subs = self.read_inbound()
        for realm, objs in read_subs.items():
            self.kernel_comm_pool.apply_async(
                func=publish,
                args=(
                    objs,
                    self.processed_submissions,
                    self.rtdb,
                ))

    def load_failed(self) -> None:
        fb_utils.get_failed_objects(self.inbound, self.rtdb)
        fc_sub = self.processed_submissions.qsize()
        _logger.info(f'Loaded failed: {fc_sub}')

    def read_inbound(self):
        pass


def publish(objs: List[Any], queue: Queue, rtdb=None):
    if not objs:
        return 0

    try:
        # send data
        for obj in objs:
            fb_utils.remove_from_cache(obj, rtdb)
            fb_utils.remove_from_quarantine(obj, rtdb)
        return len(objs)
    # TODO handle expected errors
    except Exception:  # bad_request / needs quarantine?
        return handle_kernel_errors(objs, queue, rtdb)
    except Exception as no_connection:
        _logger.warning(f'Unexpected Response: {no_connection}')
        fb_utils.cache_objects(objs, queue, rtdb)
        return 0


def handle_kernel_errors(objs: List[Any], queue: Queue, rtdb=None):
    _size = len(objs)
    if _size > 1:
        # break down big failures and retry parts
        # reducing by half each time
        _chunks = fb_utils.halve_iterable(objs)
        _logger.debug(f'Trying smaller chunks than {_size}...')
        return sum([publish(chunk, queue, rtdb) for chunk in _chunks])

    # Move bad object from cache to quarantine
    for obj in objs:
        fb_utils.remove_from_cache(obj, rtdb)
    fb_utils.quarantine(objs, rtdb)
    return 0
