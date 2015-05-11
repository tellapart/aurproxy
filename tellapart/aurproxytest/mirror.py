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
import os
import unittest

from tellapart.aurproxy.mirror import (
  _FALLBACK_MSG,
  load_mirror_updater,
  MirrorUpdater)
from tellapart.aurproxy.config import SourceEndpoint


def dummy_update(self, kill_running=True):
  self._needs_update = False

class MirrorUpdaterTests(unittest.TestCase):
  def test_mirror_updater(self):
    '''
    Tests MirrorUpdater update flag status and command contents when creating,
    adding, removing, and eliminating endpoints.
    '''
    static_source_config = json.dumps({
      "source_class": "tellapart.aurproxy.source.StaticProxySource",
      "host": "127.0.0.1",
      "name": "base",
      "port": 80
    })

    # Load up a mirror updater
    mirror_updater = load_mirror_updater(source_config=static_source_config,
                                         ports='8080,8081',
                                         max_qps=100,
                                         max_update_frequency=15)

    # Patch in the dummy update function
    funcType = type(MirrorUpdater.update)
    mirror_updater.update = funcType(dummy_update,
                                     mirror_updater,
                                     MirrorUpdater)

    # Correct the template path for test time
    template_path = os.path.join(os.path.dirname(__file__),
                                 '../../templates/gor/mirror.sh.template')
    mirror_updater._template_path = template_path

    # Check that update signals flow correctly through to command
    # Initial setup
    self.assertTrue(mirror_updater._should_update())
    mirror_updater.set_up()
    self.assertTrue('127.0.0.1:80' in mirror_updater._generate_command())
    self.assertFalse(mirror_updater._should_update())

    # Add a new endpoint
    mirror_updater._source.add(SourceEndpoint('127.0.0.1', 81))
    self.assertTrue(mirror_updater._should_update())
    mirror_updater.update()
    self.assertTrue('127.0.0.1:81' in mirror_updater._generate_command())
    self.assertFalse(mirror_updater._should_update())

    # Remove the new endpoint
    mirror_updater._source.remove(SourceEndpoint('127.0.0.1', 81))
    self.assertTrue(mirror_updater._should_update())
    mirror_updater.update()
    self.assertTrue('127.0.0.1:81' not in mirror_updater._generate_command())

    # Remove the only remaining endpoint
    mirror_updater._source.remove(SourceEndpoint('127.0.0.1', 80))
    self.assertTrue(mirror_updater._should_update())
    mirror_updater.update()
    self.assertTrue('127.0.0.1:80' not in mirror_updater._generate_command())
    self.assertTrue(_FALLBACK_MSG in mirror_updater._generate_command())


if __name__ == '__main__':
    unittest.main()
