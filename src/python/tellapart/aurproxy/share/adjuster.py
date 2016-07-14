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

from abc import (
  ABCMeta,
  abstractmethod,
  abstractproperty)

class ShareAdjuster(object):
  """Class that adjusts the share of traffic that an endpoint should receive.
  """

  __metaclass__ = ABCMeta

  def __init__(self, endpoint, signal_update_fn):
    """
    Args:
      endpoint - Endpoint to adjust.
      signal_update_fn - function - function to call on status update.
    """
    self._endpoint = endpoint
    self._signal_update_fn = signal_update_fn

  @abstractmethod
  def start(self):
    """Start maintaining share adjustment factor for endpoint.
    """

  @abstractmethod
  def stop(self):
    """Stop maintaining share adjustment factor for endpoint.
    """

  @abstractproperty
  def auditable_share(self):
    """Return a tuple containing a share adjustment factor that is a float
    between 0.0 and 1.0 as well as an aurproxy.AuditItem that includes
    debugging information about how the share value was calculated.
    """
