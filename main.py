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


# Required ENVs
'''
KAFKA_URL
KAFKA_SECURITY_PROTOCOL
KAFKA_SASL_MECHANISM
KAFKA_SASL_USERNAME
KAFKA_SASL_PASSWORD
FIREBASE_URL (string) URL of the RTDB instance
SYNC_PATH (string) base path for the SYNC storage structure
    like: {sync_path}/{doc_type}/{documents, schema, options}
TENANT (string) name of the tenant, used to prepend the Kafka topics
    like: {TENANT}.logiak.{doc_type}
'''

# optional
'''
COERSCE_ON_FAILURE (present) indicates whether we should try to cast values of non-compliant
    messages using the data types indicated in the schema
NULL_VALUE (string)  a value used in the source message to indicate None like "novalue"
MAX_KAFKA_MESSAGE_SIZE (int) maximum size for a single kafka message
'''


def run_exporter(data, context):
    try:
        from cloud.exporter import ExportManager
        man = ExportManager()
        man.run()
    except Exception as err:
        LOG.critical('Export failed!')
        LOG.critical(err)


# Required ENVs.

# SUBSCRIBE_PATTERN
# where the function will listen, including the wildcards like
# Same as provided to GCP in the function def
# {deployment_id}/data/{doc_type}/{doc_id}

# PATH_TEMPLATE
# where the function will write in RTDB, including wildcards from subscribe pattern
# /{deployment_id}/_sync_queue/{doc_type}/documents/{doc_id}

# FIREBASE_URL
# https://{app_name}.firebaseio.com/

# optional
'''
HASH_PATH (string) base path for hashes -> ({hash_path}/{doc_type}/{doc_id}) like '_hash'
'''


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
