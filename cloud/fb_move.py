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


import json

import firebase_admin

from aet.logger import get_logger

from .config import get_function_config
from . import fb_utils

LOG = get_logger('mv')
CONF = get_function_config()
RTDB = None


def __context_params(context):
    res = {}
    for i in context.params:
        try:
            res[i] = getattr(context.params, i)
        except AttributeError:
            return None
    return res


def _init_global_firebase():
    global RTDB
    if not RTDB:
        LOG.debug('initializing RTDB connection')
        app = firebase_admin.initialize_app(options={
            'databaseURL': CONF.get('FIREBASE_URL')
        })
        RTDB = fb_utils.RTDB(app)


def _make_wildcard_writer():
    # requires `doc_type` etc be passed in as a wildcard
    # then picked up from the context.params dict
    # like:
    # /some/path/{doc_type}/{maybe_an_id}
    # format specified in CONF.path_template
    LOG.debug('Creating writer (wildcard)')
    target_path = CONF.get('PATH_TEMPLATE')
    sync_path = CONF.get('SYNC_PATH')
    _init_global_firebase()

    def _writer(data, context):
        LOG.debug(f'change on {context.resource}')
        doc = data['value']
        params = __context_params(context)
        params['sync_path'] = sync_path
        target = target_path.format(**params)
        ref = RTDB.reference(target)
        ref.set(json.dumps(doc))

    LOG.debug('writer ready')
    return _writer
