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

from datetime import (
  datetime,
  timedelta)
import itertools
import unittest

from tellapart.aurproxy.config import SourceEndpoint
from tellapart.aurproxy.source import SourceGroupManager
from tellapart.aurproxy.source.manager import SIGNIFICANCE
from tellapart.aurproxy.util import load_klass_factory
from tellapart.aurproxytest.source.source import (
  SourceCallbackScope,
  TstSource)

class SourceManagerCallbackScope(object):
  def __init__(self):
    self.reset()

  def reset(self):
    self.update_signaled = False

  def signal_update_fn(self):
    self.update_signaled = True

class TstSourceBuilder(object):
  def __init__(self, endpoints, share_adjuster_factories):
    self._endpoints = endpoints
    self._share_adjuster_factories = share_adjuster_factories

  def build(self):
    '''
    Returns: generated_source, callback_scope, original_endpoints.
    '''
    cb_scope = SourceCallbackScope()
    source = TstSource(name='source_' + '_'.join([str(ep.port)
                                                  for ep in self._endpoints]),
                       initial_endpoints=self._endpoints,
                       signal_update_fn=cb_scope.signal_update_fn,
                       share_adjuster_factories=self._share_adjuster_factories)
    return source, cb_scope, self._endpoints

class SourceManagerTests(unittest.TestCase):

  def test_source_manager(self):
    # Validation Functions
    def val_len(manager, source_endpoint_groups, sources, source_cb_scopes,
                overflow_endpoint_groups, overflow_sources,
                overflow_source_cb_scopes, overflow_threshold,
                weight_adj_start):
      '''
      Validate that the expected number of endpoints are returned.
      '''
      eps = list(itertools.chain(*source_endpoint_groups))
      oeps = list(itertools.chain(*overflow_endpoint_groups))
      self.assertEqual(len(manager.endpoints), len(eps) + len(oeps))

    def val_eps(manager, source_endpoint_groups, sources, source_cb_scopes,
                overflow_endpoint_groups, overflow_sources,
                overflow_source_cb_scopes, overflow_threshold,
                weight_adj_start):
      '''
      Validate that the expected endpoints are returned.
      '''
      eps = list(itertools.chain(*source_endpoint_groups))
      oeps = list(itertools.chain(*overflow_endpoint_groups))
      for ep in eps:
        self.assertIn(ep, manager.endpoints)
      for oep in oeps:
        self.assertIn(oep, manager.endpoints)

    def val_weights_all_healthy(manager, source_endpoint_groups, sources,
                            source_cb_scopes, overflow_endpoint_groups,
                            overflow_sources, overflow_source_cb_scopes,
                            overflow_threshold, weight_adj_start):
      '''
      Validate that when the service is healthy, all endpoints are present and
      weighted correctly.
      '''
      eps = list(itertools.chain(*source_endpoint_groups))
      oeps = list(itertools.chain(*overflow_endpoint_groups))
      for ep in manager.endpoints:
        if ep in eps:
          self.assertEqual(ep.weight, SIGNIFICANCE)
        elif ep in oeps:
          self.assertEqual(ep.weight, 0)
        else:
          raise Exception('Unknown endpoint.')

    def val_weights_overflow_m_src(manager, source_endpoint_groups, sources,
                                   source_cb_scopes, overflow_endpoint_groups,
                                   overflow_sources, overflow_source_cb_scopes,
                                   overflow_threshold, weight_adj_start):
      '''
      Validate that when passing the overflow threshold, all endpoints are
      present and weighted correctly.
      '''
      eps = list(itertools.chain(*source_endpoint_groups))
      oeps = list(itertools.chain(*overflow_endpoint_groups))
      min_healthy = int(len(eps) * float(overflow_threshold) / float(100))
      min_unhealthy = len(eps) - min_healthy

      # Set share to 0 for enough endpoints to reach or almost reach the
      # unhealthy threshold
      for i in range(min_unhealthy):
        ith_ep = source_endpoint_groups[0][i]
        sh_calcs = manager._share_calcs[sources[0]]
        sh_calcs[ith_ep]._share_adjusters[0].set_share(0.0)

      # Overflow shouldn't be on yet.
      for ep in manager.endpoints:
        if ep in oeps:
          self.assertEqual(ep.weight, 0)

      # Regular endpoints serving
      num_reg_serving = len([ep for ep in manager.endpoints
                             if ep.weight > 0 and ep in eps])
      if weight_adj_start == now:
        # Not all regular endpoints should be serving
        self.assertEqual(num_reg_serving, min_healthy)
      else:
        # Regular endpoints should be serving weight adjustment hasn't started.
        self.assertEqual(num_reg_serving, len(eps))

      # Overflow endpoints serving
      num_o_serving = len([ep for ep in manager.endpoints
                             if ep.weight > 0 and ep in oeps])
      # No overflow endpoints should be serving
      self.assertEqual(num_o_serving, 0)

      # Turn off one more regular endpoint
      sh_calcs = manager._share_calcs[sources[0]]
      sh_calc = sh_calcs[source_endpoint_groups[0][min_unhealthy+1]]
      sh_calc._share_adjusters[0].set_share(0.0)

      # Regular endpoints serving
      num_reg_serving = len([ep for ep in manager.endpoints
                             if ep.weight > 0 and ep in eps])
      if weight_adj_start == now:
        # Not all regular endpoints should be serving
        self.assertEqual(num_reg_serving, min_healthy-1)
        sum_overflow_weight = 0
        for ep in manager.endpoints:
          if ep in oeps:
            sum_overflow_weight += ep.weight
        self.assertGreater(sum_overflow_weight, 0)
      else:
        # Regular endpoints should be serving weight adjustment hasn't started.
        self.assertEqual(num_reg_serving, len(eps))

      # Overflow endpoints serving
      num_o_serving = len([ep for ep in manager.endpoints
                             if ep.weight > 0 and ep in oeps])
      if weight_adj_start == now:
        # Overflow endpoints should be serving
        self.assertGreater(num_o_serving, 0)
      else:
        self.assertEqual(num_o_serving, 0)

    def val_shares_m_src(manager, source_endpoint_groups, sources,
                         source_cb_scopes, overflow_endpoint_groups,
                         overflow_sources, overflow_source_cb_scopes,
                         overflow_threshold, weight_adj_start):
      '''
      Validate that when multiple share adjusters are applied, all endpoints
      are present and weighted correctly.
      '''
      if len(sources[0].share_adjuster_factories) < 2:
        raise Exception('Validator must be run on source with at least 2 share'
                        'adjuster factories registered.')
      if len(sources[0].endpoints) == 0:
        raise Exception('Validator must be run on source with at least one'
                        'endpoint.')
      eps = list(itertools.chain(*source_endpoint_groups))
      # Share calculator for one endpoint
      sh_calc = manager._share_calcs[sources[0]][source_endpoint_groups[0][0]]
      # Set share to 0.5 for 2 sibling adjusters - .5 * .5 -> expect .25
      sh_calc._share_adjusters[0].set_share(0.5)
      sh_calc._share_adjusters[1].set_share(0.5)
      if weight_adj_start == now:
        sorted_eps = sorted(manager.endpoints, key=lambda x: x.weight)
        lowest = sorted_eps[0]
        rest = sorted_eps[1:]
        for ep in rest:
          self.assertTrue(float(lowest.weight)/float(ep.weight) == 0.25)
      else:
        num_reg_serving = len([ep for ep in manager.endpoints
                              if ep.weight > 0 and ep in eps])
        self.assertEqual(num_reg_serving, len(eps))

    # Group standard validation functions
    val_fns = [
      val_len,
      val_eps,
      val_weights_all_healthy
    ]
    # Overflow validation functions
    o_val_fns = [
      val_weights_overflow_m_src
    ]
    # Share validation functions
    share_val_fns = [
      val_shares_m_src
    ]

    # Parameter group parts
    # Source endpoints
    s_1_eps = [SourceEndpoint('127.0.0.1', i) for i in range(8000, 8005)]
    s_2_eps = [SourceEndpoint('127.0.0.1', i) for i in range(9000, 9005)]
    # Overflow source endpoints
    os_1_eps = [SourceEndpoint('127.0.0.1', i) for i in range(10000, 10005)]

    # Share adjuster factory groups
    tst_adjuster = 'tellapart.aurproxytest.share.adjuster.TstShareAdjuster'
    tst_sh_adj_fact = load_klass_factory(tst_adjuster)

    # Source Builders
    s_src_no_sh_adj = [TstSourceBuilder(s_1_eps, [])]
    s_src_m_sh_adj = [TstSourceBuilder(s_1_eps, [tst_sh_adj_fact,
                                                 tst_sh_adj_fact])]
    m_src_no_sh_adj = [TstSourceBuilder(s_1_eps, []),
                       TstSourceBuilder(s_2_eps, [])]
    no_osrc_no_sh_adj = []
    s_osrc_no_sh_adj = [TstSourceBuilder(os_1_eps, [])]
    m_src_s_sh_adj = [TstSourceBuilder(s_1_eps, [tst_sh_adj_fact]),
                      TstSourceBuilder(s_2_eps, [])]

    # Start times
    now = datetime.now()
    future = now + timedelta(days=1)

    # Overflow Threshold Percentages
    thr_none = None
    thr_80 = 80

    # Parameter groups
    #  source_builders
    #  overflow_source_builders
    #  overflow_threshold_pct,
    #  weight_adjustment_start time,
    #  validation_fns
    pgroups = [
      (s_src_no_sh_adj, no_osrc_no_sh_adj, thr_none, now, val_fns),
      (s_src_no_sh_adj, no_osrc_no_sh_adj, thr_none, future, val_fns),
      (s_src_m_sh_adj, no_osrc_no_sh_adj, thr_none, now,
       val_fns+share_val_fns),
      (s_src_m_sh_adj, no_osrc_no_sh_adj, thr_none, future,
       val_fns+share_val_fns),
      (m_src_no_sh_adj, no_osrc_no_sh_adj, thr_none, now, val_fns),
      (m_src_no_sh_adj, no_osrc_no_sh_adj, thr_none, future, val_fns),
      (m_src_s_sh_adj, s_osrc_no_sh_adj, thr_80, now, val_fns+o_val_fns),
      (m_src_s_sh_adj, s_osrc_no_sh_adj, thr_80, future, val_fns+o_val_fns),
    ]

    # Helper to build source and related validation items.
    def build_sources(builders):
      srcs, cb_scopes, ep_groups = [], [], []
      for builder in builders:
        src, cb_scope, eps = builder.build()
        srcs.append(src)
        cb_scopes.append(cb_scope)
        ep_groups.append(eps)
      return srcs, cb_scopes, ep_groups

    # Run validators against parameter groups
    for src_builders, o_src_builders, o_thresh, w_adj_start, v_fns in pgroups:
      for validation_fn in v_fns:
        manager_cb_scope = SourceManagerCallbackScope()
        srcs, src_cb_scopes, src_ep_groups = build_sources(src_builders)
        o_srcs, o_src_cbs, o_src_ep_groups = build_sources(o_src_builders)

        signal_update_fn = manager_cb_scope.signal_update_fn
        manager = SourceGroupManager(sources=srcs,
                                     overflow_threshold_pct=o_thresh,
                                     overflow_sources=o_srcs,
                                     signal_update_fn=signal_update_fn)
        manager.start(weight_adjustment_start=w_adj_start)
        validation_fn(manager, src_ep_groups, srcs, src_cb_scopes,
                      o_src_ep_groups, o_srcs, o_src_ep_groups, o_thresh,
                      w_adj_start)

if __name__ == '__main__':
    unittest.main()
