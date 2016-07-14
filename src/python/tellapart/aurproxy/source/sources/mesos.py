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

from __future__ import absolute_import
import json

from gevent.lock import RLock

from .serverset import (
  Endpoint,
  Member,
  ServerSet,
  ServerSetSource
)

class MesosMasterProxySource(ServerSetSource):

  def __init__(self,
      mesos_master_path,
      zk_servers,
      **kwargs):
    self._members = {}
    self._current_leader = None
    self._member_lock = RLock()
    self._zk_server_set = None
    self._next_on_join = self._on_join(mesos_master_path)
    self._next_on_leave = self._on_leave(mesos_master_path)

    super(MesosMasterProxySource, self).__init__(mesos_master_path, zk_servers, **kwargs)

  def _parse_member(self, node, data):
    js_data = json.loads(data)

    ep = Endpoint(js_data['hostname'], int(js_data['port']))
    member = Member(node, ep, {}, 0, 'ALIVE')
    return member

  def _get_leader(self):
    # The current leader is the node with the lowest ID.
    sorted_members = sorted(self._members.items(), key=lambda m: m[0])
    if any(sorted_members):
      return sorted_members[0][1]
    else:
      return None

  def _maybe_notify_leader_change(self):
    leader = self._get_leader()
    # The leader has left and we have a current leader, remove it
    if not leader and self._current_leader:
      del self._server_set[:]
      self._next_on_leave(self._current_leader)
    # We either don't have a current leader, or the leader has changed
    elif not self._current_leader or leader.name != self._current_leader.name:
      if self._current_leader:
        del self._server_set[:]
        self._next_on_leave(self._current_leader)
      self._current_leader = leader
      if leader:
        self._server_set.append(leader)
        self._next_on_join(leader)

  def __on_node_join(self, m):
    with self._member_lock:
      self._members[m.name] = m
      self._maybe_notify_leader_change()

  def __on_node_leave(self, m):
    with self._member_lock:
      self._members.pop(m.name)
      self._maybe_notify_leader_change()

  def _get_server_set(self):
    with self._member_lock:
      server_set = ServerSet(self._zk,
        self._zk_path,
        on_join=self.__on_node_join,
        on_leave=self.__on_node_leave,
        member_filter=lambda m: m.startswith('json.info_'),
        member_factory=self._parse_member
      )
      self._zk_server_set = server_set
      servers = server_set.get_members()
      ret = []
      if any(servers):
        # The logic to figure out the current leader is to take the node
        # with the lowest id.  This means we can just sort the nodes by name
        # and take the first one.
        # See http://zookeeper.apache.org/doc/trunk/recipes.html#sc_leaderElection
        self._current_leader = sorted(servers, key=lambda s: s.name)[0]
        ret = [self._current_leader]
    return ret
