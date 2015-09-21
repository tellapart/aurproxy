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

import json
import posixpath
import gevent
from gevent.event import Event
from gevent.queue import Queue
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError
from kazoo.handlers.gevent import SequentialGeventHandler
from kazoo.recipe.watchers import (
  ChildrenWatch,
  DataWatch)

from tellapart.aurproxy.config import SourceEndpoint
from tellapart.aurproxy.source import ProxySource
from tellapart.aurproxy.util import get_logger, slugify


logger = get_logger(__name__)

_ZK_MAP = {}


class ServerSetSource(ProxySource):

  def __init__(self,
               path,
               zk_servers,
               endpoint=None,
               signal_update_fn=None,
               share_adjuster_factories=None,
               zk_member_prefix=None):
    super(ServerSetSource, self).__init__(signal_update_fn,
                                          share_adjuster_factories)
    self._zk_path = path
    self._zk_servers = zk_servers
    self._endpoint = endpoint
    self._server_set = []
    self._zk_member_prefix = zk_member_prefix

  @property
  def blueprint(self):
    return None

  @property
  def slug(self):
    return slugify('{0}__{1}'.format(self._zk_path, self._endpoint))

  def start(self):
    global _ZK_MAP
    if not self._zk_servers in _ZK_MAP:
      _ZK_MAP[self._zk_servers] = self._get_kazoo_client()
    self._server_set = self._get_server_set()
    [ self.add(self._get_endpoint(s)) for s in self._server_set ]

  def stop(self):
    [ self.remove(self._get_endpoint(s)) for s in self._server_set ]

  @property
  def _zk(self):
    return _ZK_MAP[self._zk_servers]

  def _get_endpoint(self, service_instance):
    if self._endpoint:
      ep = service_instance.additional_endpoints.get(self._endpoint)
    else:
      ep = service_instance.service_endpoint
    port_map = {}
    for k, v in service_instance.additional_endpoints.items():
      port_map[k] = v.port
    return SourceEndpoint(host=ep.host,
                          port=ep.port,
                          context={'port_map': port_map})

  def _get_kazoo_client(self):
    kc = KazooClient(
      hosts=self._zk_servers,
      timeout=30.0,
      handler=SequentialGeventHandler(),
      randomize_hosts=True)
    kc.start()
    return kc

  def _get_server_set(self):
    kwargs = {}
    if self._zk_member_prefix:
      kwargs['member_filter'] = lambda m: m.startswith(self._zk_member_prefix)

    server_set = ServerSet(self._zk,
                           self._zk_path,
                           on_join=self._on_join(self._zk_path),
                           on_leave=self._on_leave(self._zk_path),
                           **kwargs)
    return server_set

  def _set_needs_update(self, old_status, new_status):
    self._needs_update = True

  def _on_join(self, _):
    def __on_join(service_instance):
      self.add(self._get_endpoint(service_instance))
    return __on_join

  def _on_leave(self, _):
    def __on_leave(service_instance):
      self.remove(self._get_endpoint(service_instance))
    return __on_leave

LOG = logger

class Endpoint(object):
  """Represents an endpoint in ZooKeeper
  """

  def __init__(self, host, port):
    self._host = host
    self._port = port

  def _key(self):
    return self.host, self.port

  def __eq__(self, other):
    return isinstance(other, self.__class__) and self._key() == other._key()

  def __hash__(self):
    return hash(self._host) ^ hash(self._port)

  @property
  def host(self):
    return self._host

  @property
  def port(self):
    return self._port

  def __str__(self):
    return '%s:%s' % (self.host, self.port)

class Member(object):
  """Represents an instance of a service in ZooKeeper.
  """

  @classmethod
  def from_node(cls, member, data):
    blob = json.loads(data)
    additional_endpoints = blob.get('additionalEndpoints')
    if additional_endpoints is None:
      raise ValueError("Expected additionalEndpoints in member data")
    service_endpoint = blob.get('serviceEndpoint')
    if service_endpoint is None:
      raise ValueError("Expected serviceEndpoint in member data")
    status = blob.get('status')
    if status is None:
      raise ValueError("Expected status in member data")

    shard = blob.get('shard')
    if shard is not None:
      try:
        shard = int(shard)
      except ValueError:
        LOG.warn('Unable to parse shard from %r' % shard)
        shard = None

    return cls(
      member=member,
      service_endpoint=Endpoint(service_endpoint['host'],
                                service_endpoint['port']),
      additional_endpoints=dict((name, Endpoint(value['host'],
                                                value['port']))
                                for name, value
                                in additional_endpoints.items()),
      shard=shard,
      status=status
    )

  def __init__(
      self,
      member,
      service_endpoint,
      additional_endpoints,
      shard,
      status):

    self._name = member
    self._service_endpoint = service_endpoint
    self._additional_endpoints = additional_endpoints
    self._status = status
    self._shard = shard

  @property
  def name(self):
    return self._name

  @property
  def service_endpoint(self):
    return self._service_endpoint

  @property
  def additional_endpoints(self):
    return self._additional_endpoints

  @property
  def status(self):
    return self._status

  @property
  def shard(self):
    return self._shard

  def __addl_endpoints_str(self):
    return ['%s=>%s' % (k, v) for k, v in self.additional_endpoints.items()]

  def __str__(self):
    return 'Member(%s, %saddl: %s, status: %s)' % (
      self.service_endpoint,
      ('shard: %s, ' % self._shard) if self._shard is not None else '',
      ' : '.join(self.__addl_endpoints_str()),
      self.status
    )

  def _key(self):
    return (
      self.service_endpoint,
      frozenset(sorted(self.__addl_endpoints_str())),
      self.status,
      self._shard)

  def __eq__(self, other):
    return isinstance(other, self.__class__) and self._key() == other._key()

  def __hash__(self):
    return hash(self._key())

ROOT_LOG = logger

class ServerSet(object):
  """A very minimal ServerSet implementation using the Kazoo Client.

  This supports only getting and watching nodes in a ZK ensemble, but is a
  drop in replacement for the twitter.common.zookeeper.ServerSet in those
  cases.
  """

  class _CallbackBlocker(object):
    def __init__(self):
      self.event = Event()
      self.event.set()
      self._count = 0

    def __enter__(self):
      if self._count == 0:
        self.event.clear()
      self._count += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
      self._count -= 1
      if self._count == 0:
        self.event.set()

    def ensure_safe(self):
      self.event.wait()

    def is_blocking(self):
      return self._count != 0

  def __init__(self, zk, zk_path, on_join=None, on_leave=None,
      member_filter=None, member_factory=Member.from_node):
    """Initialize the ServerSet, ensuring the zk_path exists.

    Args:
      zk - An instance of a Kazoo client.
      zk_path - The path to watch for children in.  If the path does not exist,
                it will be watched for creation.
      on_join - An optional function to call when members join the node.
      on_leave - An optional function to call when members leave the node.
      member_filter - An optional function to filter children from ZK.
      member_factory - A function to create a Member object from a znode.
    """
    def noop(*args, **kwargs): pass
    def true(*args, **kwargs): return True
    self._log = ROOT_LOG.getChild('[%s]' % zk_path)
    self._log.info('TellApart ServerSet initializing on path %s' % zk_path)

    if not isinstance(zk, KazooClient):
      raise TypeError('zk must be an instance of a KazooClient')

    if not zk.connected:
      raise Exception('zk must be in a connected state.')

    self._zk_path = zk_path
    self._zk = zk
    self._nodes = set()
    self._members = {}
    self._on_join = on_join or noop
    self._on_leave = on_leave or noop
    self._notification_queue = Queue(0)
    self._watching = False
    self._cb_blocker = self._CallbackBlocker()
    self._member_filter = member_filter or true
    self._member_factory = member_factory
    gevent.spawn(self._notification_worker)

    if on_join or on_leave:
      self._monitor()

  def __iter__(self):
    with self._cb_blocker:
      try:
        nodes = self._zk.get_children(self._zk_path)
      except NoNodeError:
        # The un-common case here is if the path doesn't exist,
        # instead of checking every time, assume it exists and catch the exception
        # if it doesn't.
        nodes = ()
      members = self._zk_nodes_to_members(nodes)
      return (n for n in members)

  def get_members(self):
    """Returns a list of members currently in the ServerSet.

    Note: this method makes O(n) calls to ZooKeeper,
    where n = the number of members.
    """
    return list(self)

  def _get_info(self, member):
    """Queries ZooKeeper for the data (service_instance, etc)
    given a member name.

    Args:
      member - The member (relative to zk_path) to get data for.

    Returns:
      The JSON serialized data associated with the node.
    """
    info = self._zk.get(posixpath.join(self._zk_path, member))
    return info[0]

  def _safe_zk_node_to_member(self, node):
    try:
      return self._member_factory(node, self._get_info(node))
    except NoNodeError:
      # Its possible for the ZK node to be removed between getting it
      # from the list and querying it, if so, just skip it.
      return None

  def _zk_nodes_to_members(self, nodes):
    return [m for m in (self._safe_zk_node_to_member(n) for n in nodes
                        if self._member_filter(n))
            if m]

  def _monitor(self):
    """Begins watching the ZK path for node changes.
    """
    if not self._zk.exists(self._zk_path):
      self._log.warn('Path %s does not exist, waiting for it to be created.'
               % self._zk_path)

    # Data changed will notify node on creation / deletion via
    DataWatch(self._zk, self._zk_path, self._data_changed)

  def _data_changed(self, data, stat):
    # stat == None -> the node was deleted (or doesnt exist)
    if stat is None:
      self._watching = False
      self._send_all_removed()
    elif not self._watching:
      self._watching = True
      self._begin_watch()

  def _begin_watch(self):
    self._log.info('Beginning to watch path %s' % self._zk_path)
    ChildrenWatch(self._zk, self._zk_path, self._on_set_changed)

  def _send_all_removed(self):
    for k in self._members.keys():
      member = self._members.pop(k)
      self._on_leave(member)

  def _notification_worker(self):
    """'Atomically' raise notifications for join / leave.

    Having this in a worker prevents multiple updates from interleaving with
    each other, as _zk_nodes_to_members may yield.
    """
    while True:
      work = self._notification_queue.get()
      self._cb_blocker.ensure_safe()
      try:
        new_nodes, removed_nodes = work
        new_members = self._zk_nodes_to_members(new_nodes)
        self._members.update(((m.name, m) for m in new_members))

        self._log.debug("Raising notifications for %i members joining and %i members leaving."
                 % (len(new_nodes), len(removed_nodes)))

        for m in removed_nodes:
          removed_member = self._members.pop(m, None)
          if removed_member:
            try:
              self._on_leave(removed_member)
            except Exception:
              self._log.exception('Error in OnLeave callback.')
          else:
            self._log.warn('Member %s was not found in cached set' % str(m))

        for m in new_members:
          try:
            self._on_join(m)
          except Exception:
            self._log.exception('Error in OnJoin callback.')

      except Exception:
        self._log.exception('Error in notification worker.')

  def _on_set_changed(self, children):
    """Called when the children of the watched ZK node change.
    Offloads most work to a greenlet worker thread to do the actual notificaiton.

    Args:
      children - The new set of child nodes.
    """
    children = set([c for c in children if self._member_filter(c)])
    current_nodes = set(self._nodes)
    self._nodes = children
    new_nodes = children - current_nodes
    removed_nodes = current_nodes - children
    self._log.debug("Queueing notifications")
    self._notification_queue.put((new_nodes, removed_nodes))
