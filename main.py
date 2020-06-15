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


def run_exporter(data, context):
    from .exporter import ExportManager
    man = ExportManager()
    man.run()


def test_signal(data, context):
    from aet.logger import get_logger
    LOG = get_logger('test-signal')
    LOG.debug(f'data: {data} | context: {context}')
    print(f'data: {data} | context: {context}')