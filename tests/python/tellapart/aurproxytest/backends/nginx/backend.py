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

import unittest

from tellapart.aurproxy.backends import NginxProxyBackend
from tellapart.aurproxytest.backends.backend import (
  build_proxy_configuration,
  ProxyBackendTstBase)

class NginxProxyBackendTests(ProxyBackendTstBase):

  def test_nginx_proxy_backend(self):
    config, scope = build_proxy_configuration(include_route_server=True,
                                              include_stream_server=False,
                                              include_route_share_adjusters=True,
                                              include_stream_share_adjusters=False)

    backend = NginxProxyBackend(configuration=config,
                                signal_update_fn=scope.signal_update_fn)
    self.tst_proxy_backend(backend, scope)

if __name__ == '__main__':
    unittest.main()
