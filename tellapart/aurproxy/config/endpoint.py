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

import hashlib

class EndpointBase(object):
  def __init__(self, host, port, port_map=None):
    self._host = host
    self._port = port
    self._port_map = port_map or {}

  @property
  def host(self):
    return self._host

  @property
  def port(self):
    return self._port

  @property
  def port_map(self):
    return self._port_map

class AuditableEndpointBase(EndpointBase):
  def __init__(self, host, port, audit, port_map=None):
    super(AuditableEndpointBase, self).__init__(host, port, port_map)
    self._audit = audit

  @property
  def audit(self):
    return self._audit

class ProxyEndpoint(AuditableEndpointBase):
  def __init__(self, host, port, audit, weight, port_map=None):
    super(ProxyEndpoint, self).__init__(host, port, audit, port_map)
    self._weight = weight

  @property
  def weight(self):
    return self._weight

class ShareEndpoint(AuditableEndpointBase):
  def __init__(self, host, port, share, audit, port_map=None):
    super(ShareEndpoint, self).__init__(host, port, audit, port_map)
    self._share = share

  @property
  def share(self):
    return self._share

class SourceEndpoint(EndpointBase):
  def __unicode__(self):
    return '{0}:{1}'.format(self._host, self.port)

  def __hash__(self):
    return int(hashlib.md5(self.__unicode__()).hexdigest(), 16)

  def __eq__(self, other):
    if self.host == other.host and self.port == other.port:
      return True
    else:
      return False
