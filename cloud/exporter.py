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


from typing import List

import firebase_admin

from aet.logger import get_logger

from .config import get_function_config
from . import fb_utils
from .fb_utils import InputSet, InputManager
from . import kafka_utils

_logger = get_logger('EXPORT')

CONF = get_function_config()
RTDB: fb_utils.RTDBTarget = None


class ExportManager():

    def __init__(self, rtdb=None):
        # set destination
        self._connect_firebase(rtdb)
        self.manager = InputManager(self.rtdb)

    def _connect_firebase(self, rtdb=None):
        if not rtdb:
            self._init_global_firebase()
            global RTDB
            self.rtdb = RTDB
        else:
            self.rtdb = rtdb

    def _init_global_firebase(self):
        global RTDB
        if not RTDB:
            app = firebase_admin.initialize_app(options={
                'databaseURL': CONF.get('FIREBASE_URL')
            })
            RTDB = fb_utils.RTDBTarget('', fb_utils.RTDB(app))

    def run(self):
        _logger.info('starting')
        self.process()
        _logger.info('finished')

    def process(self):
        _logger.debug('Looking for work')
        read_subs: List[InputSet] = self.manager.get_inputs()
        for _input in read_subs:
            _ct = publish(_input, self.rtdb)
            _logger.info(f'published {_ct} of type : {_input.name}')


# this was refactored from using multiprocessing, so no self context.

def publish(_input: InputSet, rtdb=None):
    # TODO look at options in InputSet and route to Kafka or Other...
    if _input.docs:
        return kafka_utils.publish(_input.docs, _input.schema, _input.name, rtdb)
    else:
        _logger.info(f'No new docs to export for type {_input.name}')
