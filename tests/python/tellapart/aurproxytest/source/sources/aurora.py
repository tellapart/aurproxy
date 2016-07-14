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

"""Test aurora integration
"""

import posixpath

import gevent
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError
from kazoo.handlers.gevent import SequentialGeventHandler
from kazoo.protocol.states import ZnodeStat
from kazoo.retry import KazooRetry

import mox
import unittest

from tellapart.aurproxy.source.sources import serverset

TEST_PATH = '/test/path'
TEST_NODE = 'member_0001'
TEST_NODE_2 = 'member_0002'
TEST_NODE_DATA = '{ "status": "ALIVE", "additionalEndpoints": {"aurora": {"host": "192.168.33.7", "port": 15508}, "http": {"host": "192.168.33.7", "port": 15508}}, "serviceEndpoint": {"host": "192.168.33.7", "port": 15508}, "shard": 0}'
TEST_NODE_PATH = posixpath.join(TEST_PATH, TEST_NODE)

TEST_NODE_2_DATA = '{ "status": "ALIVE", "additionalEndpoints": {"aurora": {"host": "192.168.33.7", "port": 15508}, "http": {"host": "192.168.33.8", "port": 15508}}, "serviceEndpoint": {"host": "192.168.33.8", "port": 15508}, "shard": 0}'
TEST_NODE_2_PATH = posixpath.join(TEST_PATH, TEST_NODE_2)

def getMockServerSet(smox):
  listeners = []
  def add_listener(listener):
    listeners.append(listener)

  zk = smox.CreateMock(KazooClient)
  zk.connected = True
  zk.handler = SequentialGeventHandler()
  zk.retry = KazooRetry()

  mock_stat = smox.CreateMock(ZnodeStat)
  mock_stat.mzxid = 1

  zk.exists(TEST_PATH).AndReturn(True)
  zk.add_listener(mox.IgnoreArg()).WithSideEffects(add_listener)
  zk.get(TEST_PATH, mox.IgnoreArg()).AndReturn((1, mock_stat))
  zk.add_listener(mox.IgnoreArg()).WithSideEffects(add_listener)

  return zk

class ZooKeeperTestCase(mox.MoxTestBase):

  def testNodeDoesntExist(self):
    zk = self.mox.CreateMock(KazooClient)
    zk.connected = True
    zk.get_children(TEST_PATH).AndRaise(NoNodeError)

    self.mox.ReplayAll()

    ss = serverset.ServerSet(zk, TEST_PATH, None, None)
    members = ss.get_members()

    self.assertEqual(0, len(members))

  def testNodeJoinAndLeave(self):
    nodes = set()
    children_listeners = []
    def on_join(node):
      nodes.add(node.service_endpoint)

    def on_leave(node):
      nodes.remove(node.service_endpoint)

    zk = getMockServerSet(self.mox)

    def get_children(path, listener):
      children_listeners.append(listener)

    # Intial call, capture the callback so we can notify
    zk.get_children(TEST_PATH, mox.IgnoreArg())\
      .WithSideEffects(get_children)\
      .AndReturn([TEST_NODE])
    zk.get(TEST_NODE_PATH).AndReturn((TEST_NODE_DATA,))

    # Call 1 -> Add node
    zk.get_children(TEST_PATH, mox.IgnoreArg()).\
      AndReturn([TEST_NODE, TEST_NODE_2])
    zk.get(TEST_NODE_2_PATH).AndReturn((TEST_NODE_2_DATA,))

    # Call 2 -> Remove node
    zk.get_children(TEST_PATH, mox.IgnoreArg())\
      .AndReturn([TEST_NODE_2])

    self.mox.ReplayAll()
    serverset.ServerSet(zk, TEST_PATH, on_join, on_leave)
    gevent.sleep(0)
    self.assertEqual(len(nodes), 1)
    gevent.sleep(0)

    children_listeners[0](None)
    gevent.sleep(0)
    self.assertEqual(len(nodes), 2)

    children_listeners[0](None)
    gevent.sleep(0)
    self.assertEqual(len(nodes), 1)

  def testNodeLeavingWhileInitializing(self):
    zk = getMockServerSet(self.mox)
    nodes = { TEST_NODE, TEST_NODE_2 }

    def remove_a_node(listener):
      nodes.remove(TEST_NODE)
      listener(None)

    def get_children(_, listener):
      gevent.spawn(lambda: remove_a_node(listener))

    def noop(_): pass

    zk.get_children(TEST_PATH, mox.IgnoreArg())\
      .WithSideEffects(get_children)\
      .AndReturn(nodes)
    # The sleep here simulates get() blocking (on a socket read for example)
    # During the sleep, the queued remove_a_node function will be executed
    # in gevent causing a change notification.  It will also remove TEST_NODE
    # from the set.
    zk.get(TEST_NODE_2_PATH)\
      .WithSideEffects(lambda _: gevent.sleep(0))\
      .AndReturn((TEST_NODE_2_DATA,))

    # The serverset should then re-pull the set of servers
    zk.get_children(TEST_PATH, mox.IgnoreArg()) \
      .AndReturn(nodes)
    zk.get(TEST_NODE_PATH).AndReturn((TEST_NODE_DATA,))
    zk.get_children(TEST_PATH).AndReturn(nodes)
    zk.get(TEST_NODE_2_PATH).AndReturn((TEST_NODE_2_DATA,))

    self.mox.ReplayAll()
    ss = serverset.ServerSet(zk, TEST_PATH, noop, noop)
    gevent.sleep(0)
    gevent.sleep(0)

    members = list(ss)
    self.assertEqual(len(members), 1)
    self.assertIn(TEST_NODE_2, map(lambda m: m.name, members))
    # make sure the gevent queue is empty
    gevent.sleep(0)

if __name__ == '__main__':
  unittest.main()
