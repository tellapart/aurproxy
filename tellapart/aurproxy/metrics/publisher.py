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

"""Base metrics client and derived implementations.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from abc import (
  ABCMeta,
  abstractmethod)

from tellapart.aurproxy.util import (
  get_logger,
  PeriodicTask)

logger = get_logger(__name__)

class FlushEngine(object):
  """Class that uses some scheduling mechanism (threading, gevent, etc.) in
  order to periodically call flush_fn.
  """

  __metaclass__ = ABCMeta

  def __init__(self, period, flush_fn):
    """
    Args:
      period - The period in seconds at which to flush.
      flush_fn - The function to call.
    """
    self._period = period
    self._flush_fn = flush_fn

  @abstractmethod
  def start(self):
    """Starts the engine.
    """

  @abstractmethod
  def stop(self):
    """Stops the engine.
    """

class ThreadFlushEngine(FlushEngine):
  """Class that uses a thread to periodically flush.
  """
  def __init__(self, period, flush_fn):
    super(ThreadFlushEngine, self).__init__(period, flush_fn)
    self._thread = PeriodicTask(self._period, self._flush_fn)

  def start(self):
    """Override of base method.
    """
    self._thread.start()

  def stop(self):
    """Override of base method.
    """
    self._thread.stop()

class MetricPublisher(object):
  """Base definition of a class intended to publish metrics to external sources.
  """
  __metaclass__ = ABCMeta

  def __init__(self, source, period=60, flush_engine=ThreadFlushEngine):
    """
    Args:
      source - The identifier to use as the source of the data when publishing.
      period - The period in seconds at which to publish metrics.
      flush_engine - The type or instance of a FlushEngine used to schedule
                     publication.
    """
    self._period = period
    self._source = source
    if isinstance(flush_engine, type):
      self._flush_engine = flush_engine(self._period, self.publish)
    else:
      self._flush_engine = flush_engine

    self._metric_stores = []
    self._started = False

  @abstractmethod
  def publish(self):
    """Publishes metrics to an external endpoint.
    """

  def register_store(self, metric_store):
    """Registers a metric store with the publisher.

    Args:
      metric_store - A MetricStore object.
    """
    # Only start flushing after registration has occurred.
    if not self._started:
      self._flush_engine.start()
      self._started = True

    self._metric_stores.append(metric_store)

class LibratoMetricPublisher(MetricPublisher):
  """Implementation of a MetricPublisher that publishes to Librato.
  """
  def __init__(self, api_user, api_token, source, period=60,
               flush_engine=ThreadFlushEngine):
    """
    Args:
      api_user - The API User for Librato.
      api_token - The API Token for Librato.
      source - The identifier to use as the source of the data when publishing.
      period - The period in seconds at which to publish metrics.
      flush_engine - The type or instance of a FlushEngine used to schedule
                     publication.
    """
    self._api_user = api_user
    self._api_token = api_token

    super(LibratoMetricPublisher, self).__init__(source, period, flush_engine)

  def _get_queue(self):
    """Gets a Librato Queue object for bulk submission of metrics.

    Returns:
      A Librato Queue object.
    """
    import librato
    from librato import Queue

    connection = librato.connect(self._api_user, self._api_token)
    return Queue(connection)

  def publish(self):
    """Override of base method.
    """
    try:
      logger.info('Publishing metrics to Librato.')
      queue = self._get_queue()
      for store in self._metric_stores:
        for metric in store.get_metrics():
          queue.add(
            name=metric.name,
            value=metric.value(),
            type=metric.metric_type.lower(),
            source=self._source,
            period=self._period,
            # Enable Service-Side aggregation by default.
            attributes={'aggregate': True})

      # The Librato queue object takes care of chunking the POSTs on submit.
      queue.submit()
    except Exception:
      logger.exception('Failed to publish metrics to Librato!')

class OpenTSDBMetricPublisher(MetricPublisher):
  """Implementation of a MetricPublisher that publishes to OpenTSDB.
  """
  def __init__(self, prefix, host, port, source, period=60,
               flush_engine=ThreadFlushEngine):
    """
    Args:
      host - hostname.
      port - host port.
      source - The identifier to use as the source of the data when publishing.
      period - The period in seconds at which to publish metrics.
      flush_engine - The type or instance of a FlushEngine used to schedule
                     publication.
    """
    self._prefix = prefix
    self._host = host
    self._port = port

    super(OpenTSDBMetricPublisher, self).__init__(source, period, flush_engine)

  def hostname(self):
    import socket
    return socket.gethostname()

  def publish(self):
    import os
    import time
    import struct
    from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_LINGER, IPPROTO_TCP, TCP_NODELAY

    """Override of base method.
    """
    try:
      logger.debug('Publishing metrics to OpenTSDB.')
      sock = socket(AF_INET, SOCK_STREAM)
      sock.settimeout(3)
      sock.connect((self._host, self._port))
      sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
      sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
      sock.setsockopt(SOL_SOCKET, SO_LINGER, struct.pack('ii', 1, 0))
      ts = int(time.time())
      for store in self._metric_stores:
        for metric in store.get_metrics():
          request = "put %s%s%s %d %f host=%s pid=%d" % (self._prefix, self._source, metric.name, ts, metric.value(),
                                                         self.hostname(), os.getpid())
          logger.debug('Publishing: %s' % (request))
          sock.sendall(request + "\n")
      sock.close()
    except Exception:
      logger.exception('Failed to publish metrics to OpenTSDB!')
