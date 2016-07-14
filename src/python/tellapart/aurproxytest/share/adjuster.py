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

from tellapart.aurproxy.audit import AuditItem
from tellapart.aurproxy.share import ShareAdjuster

class TstShareAdjuster(ShareAdjuster):

  def __init__(self,
               endpoint,
               signal_update_fn,
               self_cb=None):
    super(TstShareAdjuster, self).__init__(endpoint, signal_update_fn)
    self._share = 1.0
    if self_cb:
      self_cb(self)

  def set_share(self, share):
    self._share = share
    self._signal_update_fn()

  def start(self):
    """Start maintaining share adjustment factor for endpoint.
    """
    pass

  def stop(self):
    """Stop maintaining share adjustment factor for endpoint.
    """
    pass

  @property
  def auditable_share(self):
    """Return current share adjustment factor.
    """
    return self._share, AuditItem('delay', '1.0')
