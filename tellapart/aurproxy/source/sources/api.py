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

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'


from collections import defaultdict
from datetime import (
  datetime,
  timedelta)
import dateutil.parser
from flask import (
  Blueprint,
  request)
from flask.ext.restful import (
  abort,
  Api,
  Resource)
from gevent import spawn_later
from gevent.event import Event

from tellapart.aurproxy.exception import AurProxyConfigException
from tellapart.aurproxy.source import ProxySource
from tellapart.aurproxy.util import (
  get_logger,
  load_klass_plugin)

logger = get_logger(__name__)

_DEFAULT_SOURCE_WHITELIST = ['tellapart.aurproxy.source.StaticProxySource',
                             'tellapart.aurproxy.source.AuroraProxySource']

class ApiSource(ProxySource):
  """Source that exposes an HTTP API that supports the dynamic addition and
  removal of other sources.
  """

  def __init__(self,
               name,
               source_whitelist=_DEFAULT_SOURCE_WHITELIST,
               signal_update_fn=None,
               share_updater_factories=None):
    """
    Args:
      name - Required str name of this API source. Should be unique per
        aurproxy task instance.
      source_whitelist - Optional list(str) of source class paths that are
        allowed to be instantiated.
      signal_update_fn - Optional callback fn - used to signal need to update.
      share_updater_factories - Optional list of ShareAdjuster factories.
    """
    super(ApiSource, self).__init__(signal_update_fn, share_updater_factories)
    if not name:
      raise AurProxyConfigException(name)
    self._name = name
    self._source_whitelist = source_whitelist
    self._source_map = defaultdict(dict)
    self._blueprint = self._build_blueprint(name)

  @property
  def slug(self):
    """Configuration and URL slug for this source instance."""
    return self._name

  def start(self):
    """Start maintaining endpoint list."""
    pass

  def stop(self):
    """Stop maintaining endpoint list."""
    for source_name in self._all_managed_source_names():
      self._delete_managed_source(source_name)

  @property
  def blueprint(self):
    """Flask blueprint for HTTP API."""
    return self._blueprint

  def _build_blueprint(self, name):
    """
    Build a flask blueprint that exposes an HTTP API with endpoints for the
    addition and removal of sources.

    Args:
        name - Required str name to be used in API routes.
    """
    blueprint = Blueprint(name, __name__)
    api = Api(blueprint)
    root = self

    class DynamicSource(Resource):

      def get(self, source_name):
        managed_source = root._get_managed_source(source_name)
        if not managed_source:
          root._abort(source_name)
        else:
          return managed_source.configuration

      def delete(self, source_name):
        if not root._get_managed_source(source_name):
          root._abort(source_name)
        else:
          root._delete_managed_source(source_name)
        return '', 204

      def put(self, source_name):
        source_config = request.json.get('source')
        expiration = self._parse_expiration(request.json.get('expiration',
                                                             None))
        if not root._get_managed_source(source_name):
          root._add_managed_source(source_name, source_config, expiration)
          response_code = 201
        else:
          root._delete_managed_source(source_name)
          root._add_managed_source(source_name, source_config, expiration)
          response_code = 200

        return source_config, response_code

      def _parse_expiration(self, expiration):
        expiration_parsed = None
        if expiration:
          try:
            expiration_parsed = dateutil.parser.parse(expiration)
          except:
            msg = 'Attempt to parse expiration failed!'
            logger.exception(msg)
            raise abort(400, message=msg)
          if datetime.now() + timedelta(minutes=1) > expiration_parsed:
            msg = 'Expiration must occur at least 1 minute in the future!'
            logger.info(msg)
            raise abort(400, message=msg)
        return expiration_parsed

    class DynamicSourceList(Resource):
      def get(self):
        return root._source_map.keys()

    # List sources
    api.add_resource(DynamicSourceList,
                           '/api/source/{0}/sources'.format(name))

    # Get detail for a source
    api.add_resource(DynamicSource,
                     '/api/source/{0}/source/<source_name>/'.format(name))

    return blueprint

  def _abort(self, name):
    """
    Abort an http request with a 404.

    Args:
        name - Required source name str to be used in error message.
    """
    message = "Source {0} doesn't exist".format(name)
    abort(404, message=message)

  @property
  def endpoints(self):
    """
    List of SourceEndpoints for sources managed by this ApiSource instance.
    """
    eps = set()
    for source_name in self._all_managed_source_names():
      managed_source = self._get_managed_source(source_name)
      eps = eps | set(managed_source.source.endpoints)
    return eps

  def __on_source_add(self, source, endpoint):
    """When adding a managed source."""
    self._execute_callbacks(callbacks=self._on_add_fns,
                            source=self,
                            endpoint=endpoint)
    if self._signal_update_fn:
      self._signal_update_fn()

  def __on_source_remove(self, source, endpoint):
    """When removing a managed source."""
    self._execute_callbacks(callbacks=self._on_remove_fns,
                            source=self,
                            endpoint=endpoint)
    if self._signal_update_fn:
      self._signal_update_fn()

  def _load_source(self, source_config):
    """
    Loads a source from a source configuration string.

    Args:
      source_config - JSON string source configuration.

    Returns:
      tellapart.aurproxy.source.ProxySource instance.
    """
    source_class = source_config.get('source_class', None)
    if not source_class or source_class not in self._source_whitelist:
      message = 'Invalid source_class \'{0}\''.format(source_class)
      raise abort(403, message=message)

    source = load_klass_plugin(source_config,
                               klass_field_name='source_class')
    source.register_on_add(self.__on_source_add)
    source.register_on_remove(self.__on_source_remove)
    return source

  def _all_managed_source_names(self):
    """Names of all managed sources."""
    return self._source_map.keys()

  def _add_managed_source(self, source_name, source_config, expiration_time):
    """
    Adds a managed source.

    Args:
      source_name - name of managed source.
      source_config - JSON string source configuration for managed source.
      expiration_time - datetime at which to expire managed source.
    """
    logger.info('Adding Managed Source: {0}/{1}'.format(self._name,
                                                        source_name))
    source = self._load_source(source_config)
    exp = None
    if expiration_time:
      exp = self._build_expiration(source_name, expiration_time)
    managed_source = ManagedSource(source_name, source, source_config, exp)
    self._source_map[source_name] = managed_source
    managed_source.source.start()
    if managed_source.expiration:
      managed_source.expiration.start()

  def _delete_managed_source(self, source_name):
    """
    Deletes a managed source.

    Args:
      source_name - name of managed source to delete.
    """
    logger.info('Deleting Managed Source: {0}/{1}'.format(self._name,
                                                          source_name))
    managed_source = self._source_map.pop(source_name)
    if managed_source.expiration:
      managed_source.expiration.cancel()
    managed_source.source.stop()

  def _get_managed_source(self, source_name):
    """
    Retrieves a managed source.

    Args:
      source_name - name of managed source to retrieve.

    Returns:
      ManagedSource or None if not found.
    """
    return self._source_map.get(source_name, None)

  def _build_expiration(self, source_name, expiration_time):
    """
    Builds an Expiration object with bookkeeping callback for source deletion.

    Args:
      source_name - name of managed source to expire.
      expiration_time - datetime at which to expire managed source.

    Returns:
      Unstarted Expiration
    """
    def __cb():
      logger.info('Expiring Managed Source: {0}'.format(source_name))
      self._delete_managed_source(source_name)
    return Expiration(expiration_time, __cb)

class ManagedSource(object):
  """
  Collection of information about a source managed by ApiSource.
  """
  def __init__(self, name, source, source_config, expiration):
    """
    Args:
      name - name of ManagedSource.
      source - tellapart.aurproxy.source.ProxySource.
      source_config - JSON String config of source.
      expiration - Expiration object managing expiration lifecycle.
    """
    self.name = name
    self.source = source
    self.configuration = source_config
    self.expiration = expiration

class Expiration(object):
  """
  Manages the lifecycle of another object.
  """
  def __init__(self, expiration_time, callback):
    """
    Args:
      expiration_time - datetime at which to expire managed source.
      callback - function to call when expiration time has been reached.
    """
    self._expiration_time = expiration_time
    self._callback = callback
    self._cancel_event = Event()

  def start(self):
    """
    Start expiration countdown.
    """
    seconds = (self._expiration_time - datetime.now()).total_seconds()
    spawn_later(seconds, self._cb)

  def cancel(self):
    """
    Cancel expiration countdown.
    """
    self._cancel_event.set()

  def _cb(self):
    """
    Execute original callback.
    """
    if not self._cancel_event.is_set():
      self.cancel()
      self._callback()
