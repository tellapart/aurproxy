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

from tellapart.aurproxy.source import StaticProxySource

class StaticProxySourceTests(unittest.TestCase):
  def test_static_source(self):
    name, host, port = 'localhost', '127.0.0.1', 8080
    def noop(): pass

    static_source = StaticProxySource(signal_update_fn=noop,
                                      share_updater_factories=[],
                                      name=name,
                                      host=host,
                                      port=port)
    static_source.start()
    self.assertTrue(len(static_source.slug) > 0)
    static_endpoints = static_source.endpoints
    self.assertEqual(len(static_endpoints), 1)
    static_endpoint = static_endpoints.pop()
    self.assertEqual(static_endpoint.host, host)
    self.assertEqual(static_endpoint.port, port)

if __name__ == '__main__':
    unittest.main()
