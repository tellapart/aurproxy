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
  abstractproperty)

from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

class ProxySource(object):
  __metaclass__ = ABCMeta

  def __init__(self,
               signal_update_fn=None,
               share_adjuster_factories=None):
    self._signal_update_fn = signal_update_fn
    self._share_adjuster_factories = share_adjuster_factories or []
    self._on_add_fns = []
    self._on_remove_fns = []
    self._endpoints = set()

  @property
  def endpoints(self):
    return self._endpoints

  @abstractproperty
  def slug(self):
    pass

  @abstractproperty
  def start(self):
    pass

  def add(self, endpoint):
    if endpoint not in self._endpoints:
      logger.info('Adding endpoint: %(host)s:%(port)s',
                  {'host': endpoint.host,
                   'port': endpoint.port})
      self._endpoints.add(endpoint)
      self._execute_callbacks(callbacks=self._on_add_fns,
                              source=self,
                              endpoint=endpoint)
      if self._signal_update_fn:
        self._signal_update_fn()
    else:
      logger.info('Not adding endpoint - already known. %(host)s:%(port)s',
                  {'host': endpoint.host,
                   'port': endpoint.port})

  def remove(self, endpoint):
    if endpoint in self._endpoints:
      logger.info('Removing endpoint: %(host)s:%(port)s',
                  {'host': endpoint.host,
                   'port': endpoint.port})
      self._endpoints.remove(endpoint)
      self._execute_callbacks(callbacks=self._on_remove_fns,
                              source=self,
                              endpoint=endpoint)
      if self._signal_update_fn:
        self._signal_update_fn()
    else:
      logger.info('Not removing endpoint - not known. %(host)s:%(port)s',
                  {'host': endpoint.host,
                   'port': endpoint.port})

  def register_on_add(self, fn):
    self._on_add_fns.append(fn)

  def register_on_remove(self, fn):
    self._on_remove_fns.append(fn)

  @property
  def share_adjuster_factories(self):
    return self._share_adjuster_factories

  def _execute_callbacks(self, callbacks, **kwargs):
    for callback in callbacks:
      try:
        callback(**kwargs)
      except Exception:
        logger.exception('Error in ProxySource callback.')
        raise
