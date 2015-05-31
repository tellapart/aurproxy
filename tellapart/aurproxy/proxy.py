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

from tellapart.aurproxy.app.lifecycle import register_shutdown_handler
from tellapart.aurproxy.backends import ProxyBackendProvider
from tellapart.aurproxy.metrics.store import increment_counter
from tellapart.aurproxy.util import (
  get_logger,
  PeriodicTask)


logger = get_logger(__name__)

_METRIC_UPDATE_ATTEMPTED = 'update_attempted'
_METRIC_UPDATE_ATTEMPT_SUCCEEDED = 'update_attempt_succeeded'
_METRIC_UPDATE_ATTEMPT_FAILED = 'update_attempt_failed'

class ProxyUpdater(object):
  def __init__(self, backend, config, update_period, max_update_frequency):
    self._backend = ProxyBackendProvider.get_backend(backend,
                                                     config,
                                                     self._on_update)
    self._update_period = int(update_period)
    self._max_update_frequency = int(max_update_frequency)
    self._needs_update = True
    self._last_updated = datetime(1970, 1, 1)
    self._updating = False

  def _on_update(self):
    self._needs_update = True

  def _publish_proxy_metrics(self):
    """Publishes proxy metrics if appropriate.
    """
    if self._backend.metrics_publisher:
      self._backend.metrics_publisher.publish()

  def _should_update(self, as_of):
    # Needs an update, isn't already updating, and hasn't updated too recently
      time_since_last = as_of - self._last_updated
      return self._needs_update \
        and not self._updating \
        and not time_since_last < timedelta(seconds=self._max_update_frequency)

  @property
  def blueprints(self):
    """
    Flask blueprints describing managed APIs.
    """
    return self._backend.blueprints

  def set_up(self):
    self._start_discovery(weight_adjustment_start=None)
    self._update(restart_proxy=False)

  def start(self, weight_adjustment_delay_seconds):
    now = datetime.now()
    delay = timedelta(seconds=weight_adjustment_delay_seconds)
    weight_adjustment_start = now + delay
    self._start_discovery(weight_adjustment_start)
    self._start_updating()

  def _start_updating(self):
    # Start the ProxyUpdater
    self._proxy_task = PeriodicTask(self._update_period, self._try_update)
    register_shutdown_handler(self._proxy_task.stop)
    self._proxy_task.start()

    # Start the proxy metrics publisher task.
    self._proxy_metrics_task = PeriodicTask(self._update_period,
                                            self._publish_proxy_metrics)

    self._proxy_metrics_task.start()
    register_shutdown_handler(self._proxy_metrics_task.stop)

  def _start_discovery(self, weight_adjustment_start):
    self._backend.start_discovery(weight_adjustment_start)

  def _try_update(self, as_of=None):
    try:
      increment_counter(_METRIC_UPDATE_ATTEMPTED)
      if not as_of:
        as_of = datetime.now()

      do_update = self._should_update(as_of)
      if do_update:
        self._needs_update = False
        self._updating= True
        try:
          self._update(restart_proxy=True)
        except Exception:
          logger.exception('Failed to update configuration.')
        finally:
          self._updating = False
    except Exception:
      increment_counter(_METRIC_UPDATE_ATTEMPT_FAILED)
      logger.exception('Error updating.')

  def _update(self, restart_proxy=True):
    self._backend.update(restart_proxy)
