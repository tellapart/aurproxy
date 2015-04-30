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

class ProxyRoute(object):
  def __init__(self,
               locations,
               source_group_manager):
    self._locations = locations
    self._source_group_manager = source_group_manager

  @property
  def locations(self):
    return self._locations

  @property
  def endpoints(self):
    return self._source_group_manager.endpoints

  @property
  def slug(self):
    return self._source_group_manager.slug

  def start(self, weight_adjustment_start):
    self._source_group_manager.start(weight_adjustment_start)
