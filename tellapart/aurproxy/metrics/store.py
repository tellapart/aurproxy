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

"""Metric store and singleton instance.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

import copy

from tellapart.aurproxy.exception import AurProxyValueException
from tellapart.aurproxy.metrics import (
  Counter,
  Gauge,
  MetricType)

# Global instance of the store. Initialized on-demand.
_STORE = None

class MetricStore(object):
  """Centralized storage for a group of metrics. Allows registration of handlers
  for publishing data to external consumers.
  """
  NAME_TO_TYPE = {
    MetricType.COUNTER: Counter,
    MetricType.GAUGE: Gauge
  }
  # Separator to use when constructing a full metric string.
  SEPARATOR = '.'

  def __init__(self, root_prefix=''):
    """
    Args:
      root_prefix - Optional prefix for all metric names.
    """
    self.root_prefix = root_prefix

    self._metrics = dict()
    self._publishers = []

  def add_publisher(self, metric_publisher):
    """Adds a metric publisher.

    Args:
      metric_publisher - A MetricPublisher object.
    """
    metric_publisher.register_store(self)
    self._publishers.append(metric_publisher)

  def flush_all_publishers(self):
    """Forces all registered publishers to immediately publish.
    """
    for publisher in self._publishers:
      publisher.publish()

  def get_metrics(self):
    """Provides a thread-safe mechanism for getting all published metrics.

    Returns:
      A list of Metric objects.
    """
    metrics = copy.copy(self._metrics)
    return metrics.values()

  def _generate_metric_name(self, name):
    """Generates a metric name based on any

    Args:
      name - The base name of the metric.

    Returns:
      A new name prepended with the root prefix, if appropriate.
    """
    if self.root_prefix:
      return self.SEPARATOR.join((self.root_prefix, name))
    else:
      return name

  def _ensure_metric(self, name, metric_type):
    """Ensures that an instance of the metric exists in the metrics dictionary.

    Args:
      name - The full name of the metric.
      metric_type - The type of the metric.

    Returns:
      A Metric object.
    """
    full_name = self._generate_metric_name(name)
    metric = self._metrics.get(full_name)
    if not metric:
      metric = self.NAME_TO_TYPE[metric_type](full_name)
      self._metrics[full_name] = metric
    else:
      if metric.metric_type != metric_type:
        raise AurProxyValueException(
            'Metric type mismatch for %s. Expected: %s, got: %s',
            full_name, metric.metric_type, metric_type)

    return metric

  # Note: A registration system would probably be preferable to this method in
  # the long run so you'd be able to tell exactly which metrics are published,
  # even if no values have yet been recorded.
  def increment_counter(self, name, value=1):
    """Increments a counter by name.

    Args:
      name - The name of the counter.
      value - The value to increment by.

    Returns:
      The new value of the counter.
    """
    return self._ensure_metric(name, MetricType.COUNTER).increment(value)

  def reset_counter(self, name):
    """Resets a counter by name.

    Args:
      name - The name of the counter.
    """
    self._ensure_metric(name, MetricType.COUNTER).reset()

  def update_counter(self, name, value):
    """Updates a counter by name.

    Useful in situations where the counter is being observed, rather than
    maintained.

    Args:
      name - The name of the counter.
      value - The new value to update to.

    Returns:
      The new value of the counter.
    """
    return self._ensure_metric(name, MetricType.COUNTER).update(value)

  def update_gauge(self, name, value):
    """Updates a gauge by name.

    Args:
      name - The name of the gauge.
      value - The new value to update to.

    Returns:
      The new value of the gauge.
    """
    self._ensure_metric(name, MetricType.GAUGE).update(value)

##################################################################
# Convenience methods for interacting with the root MetricStore. #
##################################################################
def root_metric_store():
  """Returns a reference to the root singleton metric store.

  Returns:
    A MetricStore object.
  """
  global _STORE
  if not _STORE:
    _STORE = MetricStore()

  return _STORE

def set_root_prefix(prefix):
  """Sets the root prefix to be used when generating metric names.

  Args:
    prefix - The prefix string to prepend to all metric names.
  """
  root_metric_store().root_prefix = prefix

def add_publisher(metric_publisher):
  """Adds a metric publisher.

  Args:
    metric_publisher - A MetricPublisher object.
  """
  root_metric_store().add_publisher(metric_publisher)

def increment_counter(name, value=1):
  """Increments a counter by name.

  Args:
    name - The name of the counter.
    value - The value to increment by.

  Returns:
    The new value of the counter.
  """
  return root_metric_store().increment_counter(name, value)

def reset_counter(name):
  """Resets a counter by name.

  Args:
    name - The name of the counter.
  """
  root_metric_store().reset_counter(name)

def update_counter(name, value):
  """Updates a counter by name.

  Useful in situations where the counter is being observed, rather than
  maintained.

  Args:
    name - The name of the counter.
    value - The new value to update to.

  Returns:
    The new value of the counter.
  """
  return root_metric_store().update_counter(name, value)

def update_gauge(name, value):
  """Updates a gauge by name.

  Args:
    name - The name of the gauge.
    value - The new value to update to.

  Returns:
    The new value of the gauge.
  """
  root_metric_store().update_gauge(name, value)
