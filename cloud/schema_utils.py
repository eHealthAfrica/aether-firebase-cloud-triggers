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

import datetime
from typing import Tuple

import spavro.io


def _identity(x):
    return x


XF = {
    'long': lambda x: int(x),
    'int': lambda x: int(x),
    'float': lambda x: float(x),
    'double': lambda x: float(x),
    'string': lambda x: str(x),
    'timestamp-millis': lambda x: datetime.datetime.fromtimestamp(x).isoformat(),
    'time-micros': lambda x: datetime.datetime.fromtimestamp(x).isoformat(),
    'timestamp-micros': lambda x: datetime.datetime.fromtimestamp(x).isoformat(),
    'null': lambda x: None,
    'record': _identity,
    'array': _identity,
    'boolean': lambda x: bool(x)
}


def primary_type(block) -> Tuple[bool, str]:  # Tuple[nullable, avro type]
    _type = block.get('type')
    if not isinstance(_type, list):
        return (False, _type)
    elif _type[0] != 'null' or len(_type) == 0:
        return (False, _type[0])
    return (True, _type[1])


def contains_id(schema):
    for field in schema.get('fields'):
        if field.get('name') == 'id':
            return True
    return False


def add_id_field(schema, opts=None):
    if not opts or not opts.get('ID_FIELD'):
        raise RuntimeError('must include a "ID_FIELD" directive for schemas with no field "id"')
    source = opts.get('ID_FIELD')
    schema['fields'].append(
        {
            'name': 'id',
            'type': 'string',
            'description':
                f'automatically referenced ID for aether compatibility from field: {source}'
        }
    )
    return schema


def xf_iter(schema):
    for field in schema.get('fields', {}):
        _nullable, _type = primary_type(field)
        yield(field.get('name'), _nullable, XF.get(_type, _identity))


def coersce_or_fail(obj, schema, schema_dict, opts=None):
    doc = coersce(obj, schema_dict, opts)
    if not spavro.io.validate(schema, doc):
        raise ValueError('schema validation failed')
    return doc


def coersce(obj, schema_dict, opts=None):
    if not opts:
        opts = {}
    transforms = xf_iter(schema_dict)
    res = {}
    for name, _nullable, xf in transforms:
        val = obj.get(name)
        if val is not None:
            if val in [opts.get('NULL_VALUE', ""), ""] and _nullable:
                continue
            res[name] = xf(val)
    if 'id' not in res:
        _alias = opts.get('ID_FIELD')
        if not _alias:
            raise RuntimeError(
                'all entities must include a field named "id"'
                ' or set the ID_FIELD directive'
            )
        _id_value = res.get(_alias)
        if not _id_value:
            raise RuntimeError('ID field {_alias} does not contain a value')
        res['id'] = _id_value

    return res
