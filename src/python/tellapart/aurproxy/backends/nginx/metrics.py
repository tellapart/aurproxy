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

import re
import requests

from tellapart.aurproxy.metrics.store import (
  update_counter,
  update_gauge,
)
from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

class NginxProxyMetricsPublisher(object):
  """Class that polls the proxy for operational metrics and publishes them.
  """

  _ACTIVE_CONNECTIONS_RE = re.compile(r'Active connections: (?P<conn>\d+)')
  _SERVER_TOTALS_RE = re.compile('^(?P<acc>\d+)\s+(?P<hand>\d+)\s+(?P<req>\d+)')
  _SERVER_STATUS_RE = re.compile(
      'Reading: (?P<read>\d+) Writing: (?P<write>\d+) Waiting: (?P<wait>\d+)')

  _PROXY_METRICS_PREFIX = 'proxy.%s'

  def __init__(self, port, timeout=3, path='aurproxy/status'):
    """
    Args:
      port - The port to connect to.
      timeout - Timeout for the connection in seconds.
      path - The path of the status endpoint.
    """
    self._port = port
    self._timeout = timeout
    self._path = path

  def publish(self):
    """Fetch and publish proxy metrics.
    """
    logger.info('Publishing proxy metrics.')
    url = 'http://localhost:%s/%s' % (self._port, self._path)
    try:
      res = requests.get(url, timeout=self._timeout)
      if res.status_code != 200:
        logger.error(
            'Failed fetch proxy metrics for %s. Status code: %s',
            url, res.status_code)

      lines = [l.strip() for l in res.text.split('\n') if l]

      # Number of current active connections on the server.
      active = int(self._ACTIVE_CONNECTIONS_RE.match(lines[0]).group('conn'))
      update_gauge(self._get_metric_name('active_connections'), active)

      # Total accepts/handled/requests seen since the server started.
      server = self._SERVER_TOTALS_RE.match(lines[2])
      update_counter(
          self._get_metric_name('total_accepts'), int(server.group('acc')))
      update_counter(
          self._get_metric_name('total_handled'), int(server.group('hand')))
      update_counter(
          self._get_metric_name('total_requests'), int(server.group('req')))

      # Current number of Reading/Writing/Waiting.
      status = self._SERVER_STATUS_RE.match(lines[3])
      update_gauge(
          self._get_metric_name('reading'), int(status.group('read')))
      update_gauge(
          self._get_metric_name('writing'), int(status.group('write')))
      update_gauge(
          self._get_metric_name('waiting'), int(status.group('wait')))
    except Exception:
      logger.exception('Failed to fetch proxy metrics for %s.', url)

  def _get_metric_name(self, postfix):
    """Returns a full metric name based on the postfix.

    Args:
      postfix - The postfix of the metric name.

    Returns:
      A string representing the full metric name.
    """
    return self._PROXY_METRICS_PREFIX % postfix
