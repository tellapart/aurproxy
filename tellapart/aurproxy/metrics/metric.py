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

"""Classes implementing basic metric types.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from tellapart.aurproxy.exception import AurProxyValueException


class MetricType(object):
  """Enum of all supported metric types.
  """
  GAUGE = 'GAUGE'
  COUNTER = 'COUNTER'

class Metric(object):
  """Defines basic properties of a Metric.
  """
  def __init__(self, name, value=None, metric_type=None):
    """
    Args:
      name - The name of the metric.
      value - The initial value of the metric.
      metric_type - The type of metric.
    """
    if name is None:
      raise AurProxyValueException('Metric name cannot be None.')

    self._value = value
    self.name = name
    self.metric_type = metric_type

  def value(self):
    """Returns the current value of the metric.
    """
    return self._value

class Counter(Metric):
  """Defines a monotonically increasing Counter.
  """
  def __init__(self, name, value=0):
    """
    Args:
      name - The name of the counter.
      value - The initial value of the counter.
    """
    super(Counter, self).__init__(name, value, metric_type=MetricType.COUNTER)

  def reset(self):
    """Resets the counter to zero.
    """
    self._value = 0

  def increment(self, value=1):
    """Increment the counter by a positive value.

    Args:
      value - The value to increment by. Must be positive.

    Returns:
      The new value of the counter.
    """
    if value < 0:
      raise AurProxyValueException('A counter can only increase in value.')

    self._value += value
    return self._value

  def update(self, value):
    """Sets the value of the counter.

    Args:
      value - The current value of the counter.

    Returns:
      The new value of the counter.
    """
    if value < 0:
      raise AurProxyValueException('A counter cannot be negative.')

    self._value = value
    return self._value

class Gauge(Metric):
  """Defines a Gauge.
  """
  def __init__(self, name, value=0):
    """
    Args:
      name - The name of the gauge.
      value - The initial value of the gauge.
    """
    super(Gauge, self).__init__(name, value, metric_type=MetricType.GAUGE)

  def update(self, value):
    """Sets the value of the gauge.

    Args:
      value - The current value of the gauge.

    Returns:
      The new value of the gauge.
    """
    self._value = value
    return self._value
