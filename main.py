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

from aet.logger import get_logger

LOG = get_logger('fn')

_writer = None


def run_exporter(data, context):
    from cloud.exporter import ExportManager
    man = ExportManager()
    man.run()


def rtdb_writer(data, context):
    LOG.debug(f'triggered from {data}: {context}')
    from cloud import fb_move
    global _writer
    if not _writer:
        _writer = fb_move._make_wildcard_writer()
    try:
        _writer(data, context)
    except Exception as err:
        LOG.error(err)


def test_signal(data, context):
    from cloud import fb_move
    print(dir(fb_move))
    LOG.debug(f'data: {data} | context: {context}')
