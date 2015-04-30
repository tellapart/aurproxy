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

from tellapart.aurproxy.backends import (
  ProxyBackend,
  ProxyBackendProvider)
from tellapart.aurproxy.config import SourceEndpoint

class BackendCallbackScope(object):
  def __init__(self):
    self.update_signaled = False
    self.source = None
    self.share_adjuster = None

  def __enter__(self):
    pass

  def __exit__(self, exc_type, exc_value, traceback):
    self.update_signaled = False

  def signal_update_fn(self):
    self.update_signaled = True

  def source_self_callback(self):
    def cb(source): self.source = source
    return cb

  def share_adjuster_self_callback(self):
    def cb(share_adjuster): self.share_adjuster = share_adjuster
    return cb

class TstProxyBackend(ProxyBackend):
  NAME = 'testbackend'

  def __init__(self, configuration, signal_update_fn):
    super(TstProxyBackend, self).__init__(configuration, signal_update_fn)

  @property
  def metrics_publisher(self):
    return None

  def restart(self):
    pass

  def update(self, restart_proxy):
    pass

def build_proxy_configuration(add_share_adjusters):
    scope = BackendCallbackScope()
    config = {
      'servers': [
        {
          'ports': [ 80 ],
          'routes': [
            {
              'locations': ['/'],
              'sources': [
                {
                  'source_class': 'tellapart.aurproxytest.source.source.'
                                  'TstSource',
                  'name': 'testsource',
                  'initial_endpoints': [SourceEndpoint('127.0.0.1', 8000)],
                  'self_cb': scope.source_self_callback()}]}]}]}

    if add_share_adjusters:
      adjusters = [{'share_adjuster_class': 'tellapart.aurproxytest.share'
                                            '.adjuster.TstShareAdjuster',
                          'self_cb': scope.share_adjuster_self_callback()}]
      config['servers'][0]['routes'][0]['sources'][0]['share_adjusters'] = \
        adjusters

    return config, scope


class ProxyBackendTstBase(unittest.TestCase):

  def tst_proxy_backend(self, backend, scope):
    now = datetime.now()

    # Check that source was initialized
    self.assertTrue(hasattr(scope, 'source'))

    # Check that share adjuster was initialized
    self.assertTrue(hasattr(scope, 'share_adjuster'))

    with scope:
      # Update should not have been signaled after initialization
      self.assertFalse(scope.update_signaled)

    with scope:
      # Update should be signaled after service_discovery start
      backend.start_discovery(weight_adjustment_start=now)
      self.assertTrue(scope.update_signaled)

    with scope:
      # Update should be signaled when explicitly signaled on backend
      backend.signal_update()
      self.assertTrue(scope.update_signaled)

    with scope:
      # Update should be signaled when a source is added
      scope.source.add(SourceEndpoint('127.0.0.1', 8080))
      self.assertTrue(scope.update_signaled)

    with scope:
      # Update should be signaled when a weight adjustment occurs
      scope.share_adjuster.set_share(.5)
      self.assertTrue(scope.update_signaled)

class ProxyBackendTests(ProxyBackendTstBase):

  def test_proxy_backend(self):
    config, scope = build_proxy_configuration(add_share_adjusters=True)
    backend = TstProxyBackend(configuration=config,
                              signal_update_fn=scope.signal_update_fn)
    self.tst_proxy_backend(backend, scope)

  def test_proxy_backend_provider(self):
    try:
      config, scope = build_proxy_configuration(add_share_adjusters=True)
      update_fn = scope.signal_update_fn
      ProxyBackendProvider.register(TstProxyBackend)
      backend = ProxyBackendProvider.get_backend(name=TstProxyBackend.NAME,
                                                 configuration=config,
                                                 signal_update_fn=update_fn)
      self.tst_proxy_backend(backend, scope)
    finally:
      ProxyBackendProvider.unregister(TstProxyBackend)

if __name__ == '__main__':
    unittest.main()
