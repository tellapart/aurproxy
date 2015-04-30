# Copyright 2015 TellApart, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from tellapart.aurproxy.config import SourceEndpoint
from tellapart.aurproxy.exception import AurProxyConfigException
from tellapart.aurproxy.source import ProxySource

class StaticProxySource(ProxySource):

  def __init__(self,
               signal_update_fn=None,
               share_updater_factories=None,
               **kwargs):
    super(StaticProxySource, self).__init__(signal_update_fn,
                                            share_updater_factories)
    self._name = kwargs.get('name')
    self._host = kwargs.get('host')
    self._port = kwargs.get('port')
    err_fmt = '"{0}" required on StaticProxySource'
    if not self._name:
      raise AurProxyConfigException(err_fmt.format('name'))
    if not self._host:
      raise AurProxyConfigException(err_fmt.format('host'))
    if not self._port:
      raise AurProxyConfigException(err_fmt.format('port'))

  @property
  def slug(self):
    return '{0}__{1}__{2}'.format(self._name,
                                  self._host,
                                  self._port)

  def start(self):
    self.add(SourceEndpoint(self._host, self._port))
