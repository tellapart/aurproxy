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

def linear(start_time, end_time, as_of):
  if start_time >= as_of:
    return 0.0
  if end_time <= as_of:
    return 1.0
  else:
    total = end_time - start_time
    elapsed = as_of - start_time
    p = float(elapsed.total_seconds()) / float(total.total_seconds())
    return p

_CURVE_FNS = {
  'linear': linear }

class RampingShareAdjuster(ShareAdjuster):
  def __init__(self,
               endpoint,
               signal_update_fn,
               ramp_delay,
               ramp_seconds,
               curve='linear',
               update_frequency=10,
               as_of=None):
    super(RampingShareAdjuster, self).__init__(endpoint, signal_update_fn)
    self._ramp_delay = ramp_delay
    self._ramp_seconds = ramp_seconds
    self._curve_fn = _CURVE_FNS[curve]
    self._update_frequency = update_frequency
    self._start_time = as_of
    self._stop_event = Event()

  def start(self):
    """Start maintaining share adjustment factor for endpoint.
    """
    if not self._start_time:
      self._start_time = datetime.now() + timedelta(seconds=self._ramp_delay)
    spawn_later(self._update_frequency, self._update)

  def stop(self):
    """Stop maintaining share adjustment factor for endpoint.
    """
    self._stop_event.set()

  def _update(self):
    if not self._stop_event.is_set():
      try:
        self._signal_update_fn()
      finally:
        if datetime.now() > self._end_time:
          self.stop()
        else:
          spawn_later(self._update_frequency, self._update)

  @property
  def _end_time(self):
    return self._start_time + timedelta(seconds=self._ramp_seconds)

  @property
  def auditable_share(self):
    """Return current share adjustment factor.
    """
    as_of = datetime.now()
    share = self._curve_fn(self._start_time,
                           self._end_time,
                           as_of)

    return share, AuditItem('ramp', str(share))
