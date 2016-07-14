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

from datetime import datetime
import unittest

from tellapart.aurproxy.backends import ProxyBackendProvider
from tellapart.aurproxy.config import SourceEndpoint
from tellapart.aurproxy.proxy import ProxyUpdater
from tellapart.aurproxytest.backends.backend import (
  build_proxy_configuration,
  TstProxyBackend)

class ProxyUpdaterTests(unittest.TestCase):
  def test_proxy_updater(self):
    arg_sets = []
    for add_s_a in [True, False]:
      config, scope = build_proxy_configuration(include_route_server=True,
                                                include_stream_server=False,
                                                include_route_share_adjusters=add_s_a,
                                                include_stream_share_adjusters=False)
      arg_sets.append((config, scope, add_s_a))

    try:
      ProxyBackendProvider.register(TstProxyBackend)
      for config, scope, add_share_adjusters in arg_sets:
        config, scope = build_proxy_configuration(include_route_server=True,
                                                  include_stream_server=False,
                                                  include_route_share_adjusters=True,
                                                  include_stream_share_adjusters=False)
        now = datetime.now()

        proxy_updater = ProxyUpdater(backend=TstProxyBackend.NAME,
                                     config=config,
                                     update_period=0,
                                     max_update_frequency=0)
        # Newly initialized proxy updater should need to update
        self.assertTrue(proxy_updater._should_update(now))
        proxy_updater._try_update(now)
        self.assertFalse(proxy_updater._should_update(now))

        # Newly started proxy updater should need to update
        proxy_updater.start(weight_adjustment_delay_seconds=0)
        self.assertTrue(proxy_updater._should_update(now))
        proxy_updater._try_update(now)
        self.assertFalse(proxy_updater._should_update(now))

        # Proxy updater that has been signaled by a source should need to
        # update
        scope.route_source.add(SourceEndpoint('127.0.0.1', 8080))
        self.assertTrue(proxy_updater._should_update(now))
        proxy_updater._try_update(now)
        self.assertFalse(proxy_updater._should_update(now))

        if add_share_adjusters:
          # Proxy updater that has been signaled by a share_adjuster should
          # need to update
          scope.route_share_adjuster.set_share(.5)
          self.assertTrue(proxy_updater._should_update(now))
          proxy_updater._try_update(now)
          self.assertFalse(proxy_updater._should_update(now))
    finally:
      ProxyBackendProvider.unregister(TstProxyBackend)

if __name__ == '__main__':
    unittest.main()
