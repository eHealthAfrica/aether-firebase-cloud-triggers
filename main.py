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

from aet.logger import get_logger

LOG = get_logger('fn')

_writer = None


def run_exporter(data, context):
    from cloud.exporter import ExportManager
    man = ExportManager()
    man.run()


def cfs_export_rtdb(data, context):
    from cloud.fb_move import Mode, DBType  # noqa
    return rtdb_writer(data, context, source=DBType.CFS, mode=Mode.PUSH)


def rtdb_export_rtdb(data, context):
    from cloud.fb_move import Mode, DBType  # noqa
    return rtdb_writer(data, context, source=DBType.RTDB, mode=Mode.PUSH)


def cfs_sync_rtdb(data, context):
    from cloud.fb_move import Mode, DBType  # noqa
    return rtdb_writer(data, context, source=DBType.CFS, mode=Mode.SYNC)


def rtdb_sync_rtdb(data, context):
    from cloud.fb_move import Mode, DBType  # noqa
    return rtdb_writer(data, context, source=DBType.RTDB, mode=Mode.SYNC)


def rtdb_writer(
    data,
    context,
    source=None,
    mode=None
):
    from cloud import fb_move
    global _writer
    if not _writer:
        _writer = fb_move._make_wildcard_writer(source, mode)
    try:
        _writer(data, context)
    except Exception as err:
        LOG.error(err)


def test_signal(data, context):
    LOG.debug(f'{data}')
    LOG.debug(f'{context}')
    LOG.debug(f'{[i for i in data]}')
    LOG.debug(f'{[i for i in data.keys()]}')
    for k in data.keys():
        LOG.debug(f'{k}: {data[k]}')
