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

from collections import defaultdict
from datetime import datetime
from gevent import spawn_later

from tellapart.aurproxy.audit import AuditItem
from tellapart.aurproxy.config import (
  ProxyEndpoint,
  ShareEndpoint)
from tellapart.aurproxy.exception import AurProxyValueException
from tellapart.aurproxy.share import ShareCalculator
from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

# Factor by which calculated shares/weights (which are often floats with
# significant digits after the decimal) are multiplied in order to
# ensure that proxy-facing weights (which have to be non-negative integers)
# don't lose too much granularity to reflect the desired weightings when
# applied by the proxy.
SIGNIFICANCE = 10000

class SourceGroupManager(object):
  """Manages weights across a group of primary and fallback sources.

  Weights are calculated across multiple endpoints while shares are calculated
  from the perspective of a single endpoint.
  """
  def __init__(self,
               sources,
               overflow_sources=None,
               overflow_threshold_pct=None,
               signal_update_fn=None):
    """
    Args:
      sources - Required list(aurproxy.source.Source) for primary traffic.
      overflow_sources - Optional list(aurproxy.source.Source) for overflow.
      overflow_threshold_pct - Optional int between 0 and 100.
      signal_update_fn - Required callback fn - used to signal need to update.
    """
    self._sources = sources
    # Sources need to signal when an endpoint is added or removed.
    for source in self._sources:
      source.register_on_add(self.on_add_endpoint)
      source.register_on_remove(self.on_remove_endpoint)
    if not signal_update_fn:
      raise AurProxyValueException('signal_update_fn required!')
    self._signal_update_fn = signal_update_fn
    self._overflow_sources = overflow_sources or []
    # Overflow sources need to signal when an endpoint is added or removed.
    for overflow_source in self._overflow_sources:
      overflow_source.register_on_add(self.on_add_endpoint)
      overflow_source.register_on_remove(self.on_remove_endpoint)
    self._overflow_threshold_pct = overflow_threshold_pct
    self._share_calcs = defaultdict(dict)
    self._weight_adjustment_start = None

  def on_add_endpoint(self, source, endpoint):
    """
    Callback for sources - used to register new endpoints.

    Args:
      source - Required aurproxy.source.Source
      endpoint - New endpoint to register.
    """
    calculator = ShareCalculator(source, endpoint, self._signal_update_fn)
    self._share_calcs[source][endpoint] = calculator
    try:
      self._share_calcs[source][endpoint].start()
    except Exception:
      logger.exception('Error starting ShareCalculator.')

  def on_remove_endpoint(self, source, endpoint):
    """
    Callback for sources - used to deregister endpoints.

    Args:
      source - Required aurproxy.source.Source
      endpoint - New endpoint to register.
    """
    try:
      if source in self._share_calcs:
        if endpoint in self._share_calcs[source]:
          try:
            self._share_calcs[source][endpoint].stop()
          except Exception:
            logger.exception('Error stopping ShareCalculator.')
          del self._share_calcs[source][endpoint]
        else:
          logger.warning('Endpoint "{0}:{1}" not found in under source "{2}" '
                         'in SourceManager'.format(endpoint.host,
                                                   endpoint.port,
                                                   source.slug))
      else:
        msg = 'Source "{0}" not found in ' \
              'SourceGroupManager.'.format(source.slug)
        logger.warning(msg)
    except Exception:
      logger.exception('Error removing endpoint.')

  @property
  def endpoints(self):
    """
    A list of ProxyEndpoints for sources managed by this SourceGroupManager.
    """
    if self._should_adjust_weight():
      return self._generate_normalized_weight_endpoints()
    else:
      return self._get_unadjusted_endpoints()

  @property
  def slug(self):
    """
    A slug string created from the slugs of all primary sources in the group.
    """
    return '__'.join([s.slug for s in self._sources])

  def _should_adjust_weight(self):
    now = datetime.now()
    if not self._weight_adjustment_start:
      return False
    if now < self._weight_adjustment_start:
      return False
    else:
      return True

  def start(self, weight_adjustment_start):
    """
    Start the sources managed by this SourceGroupManager.

    Args:
      weight_adjustment_start - datetime at which to start adjusting weights.
    """
    self._weight_adjustment_start = weight_adjustment_start
    if self._weight_adjustment_start:
      # Trigger a proxy update after the weight adjustment start time.
      now = datetime.now()
      if now < self._weight_adjustment_start:
        adjustment_td = self._weight_adjustment_start - now
        trigger_period = adjustment_td.total_seconds() + 1
        spawn_later(trigger_period, self._signal_update_fn)

    for source in self._sources:
      source.start()

    for overflow_source in self._overflow_sources:
      overflow_source.start()

  def _generate_normalized_weight_endpoints(self):
    """
    Get endpoints with weight adjustment logic applied.

    Returns:
      list(aurproxy.config.ProxyEndpoint)
    """
    # Get full lists of regular and overflow endpoints including shares from
    # the share manager.
    eps = []
    for source in self._sources:
      eps.extend(self._get_endpoints_with_shares(source))

    oeps = []
    for overflow_source in self._overflow_sources:
      oeps.extend(self._get_endpoints_with_shares(overflow_source))

    # Total shares of traffic desired by each endpoint.
    sum_ep_shares = self._sum_shares(eps)

    # Convert percentage overflow threshold into factor.
    overflow_threshold = None
    if self._overflow_threshold_pct:
      overflow_threshold = float(self._overflow_threshold_pct) / 100.0

    # Adjustment factors for calculating weights across full traffic stream.
    threshold = overflow_threshold
    eps_factor, oeps_factor = self._get_normalization_factors(sum_ep_shares,
                                                              len(eps),
                                                              threshold)

    # Normalize endpoints using calculated factors.
    norm_eps = self._normalize_endpoint_weights(eps, eps_factor)
    norm_oeps = self._normalize_endpoint_weights(oeps, oeps_factor)

    return norm_eps + norm_oeps

  def _get_unadjusted_endpoints(self):
    """
    Get endpoints without applying weight adjustment logic.

    Primary endpoints get weight 1.
    Overflow endpoints get weight 0.

    Returns:
     list(aurproxy.config.ProxyEndpoint)
    """
    eps = []
    audit_msg = 'Weight adjustment delayed.'
    if self._weight_adjustment_start:
      delay_time = self._weight_adjustment_start.isoformat()
      delay_msg = 'Starting: {0}.'.format(delay_time)
      audit_msg = '{0} {1}'.format(audit_msg, delay_msg)
    audit = AuditItem('audit', audit_msg)
    for source in self._sources:
      eps.extend([ProxyEndpoint(host=ep.host,
                                port=ep.port,
                                weight=SIGNIFICANCE,
                                audit=audit) for ep in source.endpoints])

    oweight = 0 if eps else 1
    oaudit = AuditItem('audit', 'Overflow endpoint.')
    for overflow_source in self._overflow_sources:
      for oep in overflow_source.endpoints:
        eps.append(ProxyEndpoint(host=oep.host,
                                 port=oep.port,
                                 weight=oweight,
                                 audit=oaudit))
    return eps

  def _get_endpoints_with_shares(self, source):
    """
    Gets endpoints with endpoint share calculations applied.

    Returns:
      list(aurproxy.config.ProxyEndpoint)
    """
    eps = []
    source_endpoints = source.endpoints
    for source_endpoint in source_endpoints:
      share_calc = self._share_calcs[source][source_endpoint]
      share, audit = share_calc.auditable_share
      eps.append(ShareEndpoint(host=source_endpoint.host,
                               port=source_endpoint.port,
                               share=share,
                               audit=audit))
    return eps

  def _sum_shares(self, endpoints):
    """
    Sum shares across a set of endpoints.

    Returns:
      float
    """
    sum_endpoint_shares = 0.0
    for endpoint in endpoints:
      endpoint_share = float(endpoint.share)
      if not 0 <= endpoint_share <= 1:
        raise AurProxyValueException('Endpoint self-reported invalid weight.')
      sum_endpoint_shares += endpoint_share
    return sum_endpoint_shares

  def _get_normalization_factors(self,
                                 endpoint_sum,
                                 endpoint_count,
                                 overflow_threshold=None):
    """
    Get factors by which to multiply primary and overflow endpoint weights in
    order to balance traffic according to the overflow_threshold.

    If total of primary source endpoint-claimed shares as a proportion of the
    number of primary source endpoints (total possible shares) is less than the
    overflow threshold, return factors that distribute the difference between
    the amount of traffic claimed and amount that would need to be claimed to
    reach the threshold to the overflow source.

    Args:
      endpoint_sum - float - sum of source's endpoint shares
        Traffic "claimed"/requested by endpoints.
      endpoint_count - int - number of source's endpoints
      overflow_threshold - float between 0.0 and 1.0

    Returns:
      (float(endpoint_norm_factor), float(overflow_endpoint_norm_factor))
    """
    try:
      eps_norm_factor = float(endpoint_sum) / float(endpoint_count)
    except ZeroDivisionError:
      logger.warning('No endpoints returned by regular sources.')
      eps_norm_factor = 1.0

    # Baseline - assume overflow should be off if there are regular endpoints,
    # otherwise, assume it is on.
    oeps_norm_factor = 0.0 if endpoint_count else 1.0
    if overflow_threshold:
      if eps_norm_factor < float(overflow_threshold):
        oeps_norm_factor = (1 - overflow_threshold) * eps_norm_factor
    return eps_norm_factor, oeps_norm_factor

  def _normalize_endpoint_weights(self, endpoints, normalization_factor):
    """
    Applies a normalization factor to a list of endpoints.

    Args:
      endpoints - list(aurproxy.config.SourceEndpoints)
      normalization_factor - float between 0.0 and 1.0

    Returns:
      list(aurproxy.config.ProxyEndpoint)
    """
    norm_factor = normalization_factor
    significance = SIGNIFICANCE
    proxy_endpoints = []
    for endpoint in endpoints:
      norm_weight = float(endpoint.share) * float(norm_factor)
      norm_audit_val = '{0} * {1} => {2}'.format(endpoint.share,
                                                 norm_factor,
                                                 norm_weight)
      norm_audit = AuditItem('nrm_wgt', norm_audit_val)

      norm_adj_weight = int(norm_weight * significance)
      norm_audit_val = '{0} * {1} => {2}'.format(norm_weight,
                                                 significance,
                                                 norm_adj_weight)
      norm_adj_audit = AuditItem('nrm_adj_wgt', norm_audit_val)
      audit = AuditItem('audit', [endpoint.audit,
                                  norm_audit,
                                  norm_adj_audit])

      proxy_endpoint = ProxyEndpoint(host=endpoint.host,
                                     port=endpoint.port,
                                     weight=norm_adj_weight,
                                     audit=audit)
      proxy_endpoints.append(proxy_endpoint)
    return proxy_endpoints
