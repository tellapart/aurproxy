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

from datetime import datetime, timedelta
from gevent import spawn_later
from gevent.event import Event

from tellapart.aurproxy.audit import AuditItem
from tellapart.aurproxy.share.adjuster import ShareAdjuster

class DelayStartShareAdjuster(ShareAdjuster):
  def __init__(self,
               endpoint,
               signal_update_fn,
               seconds,
               as_of=None):
    super(DelayStartShareAdjuster, self).__init__(endpoint, signal_update_fn)
    self._seconds = seconds
    self._start_time = as_of
    self._stop_event = Event()
    self._activation_time = None

  def start(self):
    """Start maintaining share adjustment factor for endpoint.
    """
    if not self._start_time:
      self._start_time = datetime.now()
    self._activation_time = self._start_time + timedelta(seconds=self._seconds)
    spawn_later(self._seconds, self._update)

  def stop(self):
    """Stop maintaining share adjustment factor for endpoint.
    """
    self._stop_event.set()

  def _update(self):
    if not self._stop_event.is_set():
      self._signal_update_fn()

  @property
  def auditable_share(self):
    """Return current share adjustment factor.
    """
    if self._start_time is None:
      raise Exception('DelayStartShareAdjuster: No start time.')

    if datetime.now() > self._activation_time:
      return 1.0, AuditItem('delay', '1.0')
    else:
      return 0.0, AuditItem('delay', '0.0')
