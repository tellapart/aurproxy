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
import copy
import httplib
import itertools

from tellapart.aurproxy.config import (
  ProxyRoute,
  ProxyServer,
  ProxyStream)
from tellapart.aurproxy.exception import AurProxyConfigException
from tellapart.aurproxy.metrics.store import increment_counter
from tellapart.aurproxy.source import SourceGroupManager
from tellapart.aurproxy.util import (
  get_logger,
  load_klass_factory,
  load_klass_plugin)

logger = get_logger(__name__)

_METRIC_SIGNAL_UPDATE_EXCEPTION = 'signal_update_exception'


class ProxyBackend(object):

  __metaclass__ = ABCMeta

  NAME = 'base'

  def __init__(self, configuration, signal_update_fn):
    self._configuration = configuration
    self._signal_update_fn = signal_update_fn
    self._context = self._load_config_item('context',
                                           self._configuration,
                                           required=False,
                                           default={})
    servers = self._load_config_item('servers',
                                     self._configuration,
                                     required=True)
    self._proxy_servers = self._load_proxy_servers(servers)
    self._started_discovery = False

  def _load_config_item(self, name, config_container,
                        default=None, required=True):
    if required and name not in config_container:
      raise AurProxyConfigException('\'{0}\' required.'.format(name))

    return config_container.get(name, default)

  def _load_proxy_servers(self, servers):
    proxy_servers = []
    for server in servers:
      proxy_server = self._load_proxy_server(server)
      proxy_servers.append(proxy_server)
    return proxy_servers

  def _load_proxy_server(self, server):
    hosts = self._load_config_item('hosts', server, required=False)
    ports = [ int(s) for s in
              self._load_config_item('ports', server, required=True)]
    healthcheck_route = self._load_config_item('healthcheck_route',
                                               server,
                                               required=False)
    routes = self._load_config_item('routes', server, required=False)
    proxy_routes = self._load_proxy_routes(routes)
    streams = self._load_config_item('streams', server, required=False)
    proxy_streams = self._load_proxy_streams(streams)

    msg = None
    if not routes and not streams:
      msg = 'At least one ProxyStream or ProxyRoute required.'
    if routes and streams:
      msg = 'HTTP and TCP balancing not supported at the same time.'
    if msg:
      raise AurProxyConfigException(msg)

    context = self._load_config_item('context',
                                     server,
                                     required=False,
                                     default={})
    return ProxyServer(hosts,
                       ports,
                       healthcheck_route,
                       proxy_routes,
                       proxy_streams,
                       context)

  def _load_proxy_routes(self, routes):
    proxy_routes = []
    for route in routes or []:
      proxy_route = self._load_proxy_route(route)
      proxy_routes.append(proxy_route)
    return proxy_routes

  def _load_proxy_route(self, route):
    locations = self._load_config_item('locations', route, required=True)
    sources = self._load_config_item('sources', route, required=True)
    proxy_sources = self._load_proxy_sources(sources)
    overflow_sources = self._load_config_item('overflow_sources',
                                              route,
                                              required=False,
                                              default=[])
    empty_endpoint_status_code = self._load_config_item(
        'empty_endpoint_status_code',
        route,
        required=False,
        default=httplib.SERVICE_UNAVAILABLE)
    proxy_overflow_sources = self._load_proxy_sources(overflow_sources)
    overflow_threshold_pct = self._load_config_item('overflow_threshold_pct',
                                                    route,
                                                    required=False)
    source_group_manager = SourceGroupManager(proxy_sources,
                                              proxy_overflow_sources,
                                              overflow_threshold_pct,
                                              self._signal_update_fn,)

    return ProxyRoute(
        locations, empty_endpoint_status_code, source_group_manager)

  def _load_proxy_sources(self, sources):
    proxy_sources = []
    for source in sources:
      proxy_source = self._load_proxy_source(source)
      proxy_sources.append(proxy_source)
    return proxy_sources

  def _load_proxy_source(self, source):
    source_copy = copy.deepcopy(source)
    share_adjusters = source_copy.pop('share_adjusters', None)
    sa_factories = []
    if share_adjusters:
      sa_factories = self._load_share_adjuster_factories(share_adjusters)

    extra_kwargs = {}
    extra_kwargs['signal_update_fn'] = self.signal_update
    extra_kwargs['share_adjuster_factories'] = sa_factories
    proxy_source = load_klass_plugin(source_copy,
                                     klass_field_name='source_class',
                                     **extra_kwargs)
    return proxy_source

  def _load_proxy_streams(self, streams):
    proxy_streams = []
    for stream in streams or []:
      proxy_stream = self._load_proxy_stream(stream)
      proxy_streams.append(proxy_stream)
    return proxy_streams

  def _load_proxy_stream(self, stream):
    sources = self._load_config_item('sources', stream, required=True)
    proxy_sources = self._load_proxy_sources(sources)
    update_fn = self._signal_update_fn
    source_group_manager = SourceGroupManager(proxy_sources,
                                              signal_update_fn=update_fn)
    return ProxyStream(source_group_manager)

  def _load_share_adjuster_factories(self, share_adjusters):
    share_adjuster_factories = []
    for share_adjuster in share_adjusters:
      share_adjuster_cp = copy.deepcopy(share_adjuster)
      share_adjuster_klass = share_adjuster_cp.pop('share_adjuster_class')
      share_adjuster_kwargs = share_adjuster_cp
      p_f = load_klass_factory(share_adjuster_klass,
                               **share_adjuster_kwargs)
      share_adjuster_factories.append(p_f)
    return share_adjuster_factories

  @property
  def blueprints(self):
    return list(itertools.chain(*[s.blueprints for s in self._proxy_servers]))

  def signal_update(self):
    if not self._signal_update_fn:
      logger.info('No signal update function set.')
      return

    try:
      self._signal_update_fn()
    except Exception:
      logger.exception("Failed to signal update.")
      increment_counter(_METRIC_SIGNAL_UPDATE_EXCEPTION)

  def start_discovery(self, weight_adjustment_start):
    if not self._started_discovery:
      self._started_discovery = True
      for server in self._proxy_servers:
        for route in server.routes:
          route.start(weight_adjustment_start)
        for stream in server.streams:
          stream.start(weight_adjustment_start)

  @abstractmethod
  def update(self, restart_proxy):
    pass

  @abstractmethod
  def restart(self):
    pass

  @abstractproperty
  def metrics_publisher(self):
    pass

_backends = dict()
class ProxyBackendProvider():
  @staticmethod
  def register(klass):
    global _backends
    if klass.NAME in _backends:
      msg = 'Backend "{0}" already registered'.format(klass.NAME)
      raise AurProxyConfigException(msg)
    _backends[klass.NAME] = klass

  @staticmethod
  def get_backend(name, configuration, signal_update_fn):
    global _backends
    return _backends[name](configuration, signal_update_fn)

  @staticmethod
  def unregister(klass):
    global _backends
    if klass.NAME in _backends:
      _backends.pop(klass.NAME)
