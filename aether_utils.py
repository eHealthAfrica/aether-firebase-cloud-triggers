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

from collections import namedtuple
from enum import Enum
from multiprocessing import Queue
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    NamedTuple,
    Union
)

from requests.exceptions import HTTPError

from aether.python.utils import request

from extractor import settings

Constants = namedtuple(
    'Constants',
    (
        'mappings',
        'mappingsets',
        'schemas',
        'schemadecorators',
        'submissions',
        'schema_id',
        'schema_definition',
    )
)


class CacheType(Enum):
    NORMAL = 1
    QUARANTINE = 2
    NONE = 3


class Task(NamedTuple):
    id: str
    tenant: str
    type: str
    data: Union[Dict, None] = None


# ARTEFACT_NAMES = Constants(
#     mappings='mappings',
#     mappingsets='mappingsets',
#     schemas='schemas',
#     schemadecorators='schemadecorators',
#     submissions='submissions',
#     schema_id='schema',
#     schema_definition='schema_definition',
# )

_logger = settings.get_logger('Utils')


def kernel_data_request(url='', method='get', data=None, headers=None, realm=None):
    '''
    Handle request calls to the kernel server
    '''

    headers = headers or {}
    headers['Authorization'] = f'Token {settings.KERNEL_TOKEN}'

    _realm = realm if realm else settings.DEFAULT_REALM
    headers[settings.REALM_COOKIE] = _realm

    res = request(
        method=method,
        url=f'{settings.KERNEL_URL}/{url}',
        json=data or {},
        headers=headers,
    )
    try:
        res.raise_for_status()
    except HTTPError as e:
        _logger.debug(e.response.status_code)
        raise e
    return res.json()
