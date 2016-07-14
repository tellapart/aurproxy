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

import operator

from tellapart.aurproxy.audit import AuditItem

class ShareCalculator(object):
  """Calculates a share for an endpoint, applying configured adjustments..

  A share is calculated from the perspective of a single endpoint vs a weight,
  which is calculated given knowledge of the shares of other endpoints.
  """
  def __init__(self, source, endpoint, signal_update_fn):
    """
    Args:
      source - Required aurproxy.source.Source.
      endpoint - Required aurproxy.config.SourceEndpoint.
      signal_update_fn - Required callback fn - used to signal need to update.
    """
    self._source = source
    self._endpoint = endpoint
    self._signal_update_fn = signal_update_fn
    share_adjusters = []
    for sa_factory in source.share_adjuster_factories:
      share_adjuster = sa_factory.build(endpoint=endpoint,
                                        signal_update_fn=signal_update_fn)
      share_adjusters.append(share_adjuster)
    self._share_adjusters = share_adjusters

  def start(self):
    """
    Start configured share adjusters.
    """
    for share_adjuster in self._share_adjusters:
      share_adjuster.start()

  def stop(self):
    """
    Stop configured share adjusters.
    """
    for share_adjuster in self._share_adjusters:
      share_adjuster.stop()

  @property
  def auditable_share(self):
    """
    Get a (float(share), AuditItem)).
    """
    share_comps = [1.0]
    share_comp_audits = [AuditItem('base', '1.0')]
    for share_adjuster in self._share_adjusters:
      share_comp, share_comp_audit = share_adjuster.auditable_share
      share_comps.append(float(share_comp))
      share_comp_audits.append(share_comp_audit)
    share = reduce(operator.mul, share_comps)
    audit = AuditItem('share', [share, share_comp_audits])
    return share, audit
