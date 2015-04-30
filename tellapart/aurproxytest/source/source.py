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

from tellapart.aurproxy.config import SourceEndpoint
from tellapart.aurproxy.source import ProxySource

class TstSource(ProxySource):

  def __init__(self,
               name,
               initial_endpoints=None,
               signal_update_fn=None,
               share_adjuster_factories=None,
               self_cb=None):
    super(TstSource, self).__init__(signal_update_fn,
                                    share_adjuster_factories)
    self._name = name
    self._initial_endpoints = initial_endpoints or []
    if self_cb:
      self_cb(self)

  @property
  def endpoints(self):
    return self._endpoints

  @property
  def slug(self):
    return self._name

  def start(self):
    [ self.add(ep) for ep in self._initial_endpoints ]

class SourceCallbackScope(object):
  def __init__(self):
    self.reset()

  def reset(self):
    self.update_signaled = False
    self.on_add_source = None
    self.on_add_endpoint = None
    self.on_remove_source = None
    self.on_remove_endpoint = None

  def signal_update_fn(self):
    self.update_signaled = True

  def on_add_fn(self, source, endpoint):
    self.on_add_source = source
    self.on_add_endpoint = endpoint

  def on_remove_fn(self, source, endpoint):
    self.on_remove_source = source
    self.on_remove_endpoint = endpoint

class SourceTests(unittest.TestCase):
  def test_source(self):
    scope = SourceCallbackScope()

    initial_endpoint = SourceEndpoint('127.0.0.1', 8080)
    tst_source = TstSource(name='test',
                           initial_endpoints=[initial_endpoint],
                           signal_update_fn=scope.signal_update_fn,
                           share_adjuster_factories=[])
    tst_source.register_on_add(scope.on_add_fn)
    tst_source.register_on_remove(scope.on_remove_fn)

    scope.reset()
    tst_source.start()
    self.assertTrue(scope.update_signaled)
    self.assertEqual(initial_endpoint, scope.on_add_endpoint)
    self.assertEqual(tst_source, scope.on_add_source)

    tst_endpoints = tst_source.endpoints
    self.assertEqual(len(tst_endpoints), 1)

    scope.reset()
    new_ep = SourceEndpoint('127.0.0.1', 8888)
    tst_source.add(new_ep)
    self.assertTrue(scope.update_signaled)
    self.assertEqual(new_ep, scope.on_add_endpoint)
    self.assertEqual(tst_source, scope.on_add_source)
    self.assertTrue(new_ep in tst_source.endpoints)

    scope.reset()
    tst_source.remove(new_ep)
    self.assertTrue(scope.update_signaled)
    self.assertEqual(new_ep, scope.on_remove_endpoint)
    self.assertEqual(tst_source, scope.on_remove_source)

if __name__ == '__main__':
    unittest.main()
