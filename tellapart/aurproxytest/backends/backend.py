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
import itertools
import unittest

from tellapart.aurproxy.backends import (
  ProxyBackend,
  ProxyBackendProvider)
from tellapart.aurproxy.config import SourceEndpoint

class BackendCallbackScope(object):
  def __init__(self):
    self.update_signaled = False
    self.route_source = None
    self.stream_source = None
    self.route_share_adjuster = None
    self.stream_share_adjuster = None

  def __enter__(self):
    pass

  def __exit__(self, exc_type, exc_value, traceback):
    self.update_signaled = False

  def signal_update_fn(self):
    self.update_signaled = True

  def route_source_self_callback(self):
    def cb(route_source): self.route_source = route_source
    return cb

  def stream_source_self_callback(self):
    def cb(stream_source): self.stream_source = stream_source
    return cb

  def route_share_adjuster_self_callback(self):
    def cb(route_share_adjuster):
      self.route_share_adjuster = route_share_adjuster
    return cb

  def stream_share_adjuster_self_callback(self):
    def cb(stream_share_adjuster):
      self.stream_share_adjuster = stream_share_adjuster
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

def build_proxy_configuration(include_route_server,
                              include_stream_server,
                              include_route_share_adjusters,
                              include_stream_share_adjusters):
    scope = BackendCallbackScope()
    config = {'servers': []}

    if include_route_server:
      route_server = {
        'ports': [ 80 ],
        'routes': [ {
            'locations': ['/'],
            'sources': [ {
                'source_class': 'tellapart.aurproxytest.source.source.'
                                'TstSource',
                'name': 'testsource',
                'initial_endpoints': [SourceEndpoint('127.0.0.1', 8000)],
                'self_cb': scope.route_source_self_callback()}]}]}

      if include_route_share_adjusters:
        adjusters = [{'share_adjuster_class': 'tellapart.aurproxytest.share'
                                              '.adjuster.TstShareAdjuster',
                      'self_cb': scope.route_share_adjuster_self_callback()}]
        route_server['routes'][0]['sources'][0]['share_adjusters'] = adjusters

      config['servers'].append(route_server)

    if include_stream_server:
      stream_server = {
        'ports': [ 80 ],
        'streams': [ {
            'sources': [ {
                'source_class': 'tellapart.aurproxytest.source.source.'
                                                     'TstSource',
                'name': 'testsource',
                'initial_endpoints': [SourceEndpoint('127.0.0.1', 8001)],
                'self_cb': scope.stream_source_self_callback()}]}]}

      if include_stream_share_adjusters:
        adjusters = [{'share_adjuster_class': 'tellapart.aurproxytest.share'
                                              '.adjuster.TstShareAdjuster',
                      'self_cb': scope.stream_share_adjuster_self_callback()}]
        stream_server['streams'][0]['sources'][0]['share_adjusters'] = \
          adjusters

      config['servers'].append(stream_server)

    return config, scope


class ProxyBackendTstBase(unittest.TestCase):

  def gen_proxy_config_arg_combinations(self):
    tf = [True, False]
    x_product = list(itertools.product(tf, tf, tf, tf))
    return [(a1, a2, a3, a4) for a1, a2, a3, a4 in x_product if a1 or a2]

  def tst_proxy_backend(self, backend, scope, has_share_adjuster=True):
    now = datetime.now()

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
      if scope.route_source:
        # Update should be signaled when a source is added
        scope.route_source.add(SourceEndpoint('127.0.0.1', 8080))
        self.assertTrue(scope.update_signaled)

    with scope:
      if scope.stream_source:
        # Update should be signaled when a source is added
        scope.stream_source.add(SourceEndpoint('127.0.0.1', 8081))
        self.assertTrue(scope.update_signaled)

    with scope:
      if scope.route_share_adjuster:
        # Update should be signaled when a weight adjustment occurs
        scope.route_share_adjuster.set_share(.5)
        self.assertTrue(scope.update_signaled)

    with scope:
      if scope.stream_share_adjuster:
        # Update should be signaled when a weight adjustment occurs
        scope.stream_share_adjuster.set_share(.5)
        self.assertTrue(scope.update_signaled)

class ProxyBackendTests(ProxyBackendTstBase):

  def test_proxy_backend(self):
    arg_combos = self.gen_proxy_config_arg_combinations()
    for inc_rt, inc_st, inc_rt_sa, inc_st_sa in arg_combos:
      config, scope = build_proxy_configuration(include_route_server=inc_rt,
                                                include_stream_server=inc_st,
                                                include_route_share_adjusters=inc_rt_sa,
                                                include_stream_share_adjusters=inc_st_sa)
      backend = TstProxyBackend(configuration=config,
                                signal_update_fn=scope.signal_update_fn)
      self.tst_proxy_backend(backend,
                             scope,
                             has_share_adjuster=inc_rt and inc_rt_sa)  # (inc_rt_sa or inc_st_sa))

  def test_proxy_backend_provider(self):
    try:
      config, scope = build_proxy_configuration(include_route_server=True,
                                                include_stream_server=False,
                                                include_route_share_adjusters=True,
                                                include_stream_share_adjusters=False)
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
