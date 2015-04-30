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

class AuditItem(object):
  def __init__(self, name, value):
    self._name = name
    self._value = value

  @property
  def name(self):
    return self._name

  @property
  def value(self):
    return self._value

  def render(self):
    audit_tree = AuditItem.generate_audit_tree(self)
    return json.dumps(audit_tree)

  @staticmethod
  def generate_audit_tree(audit_item):
    if isinstance(audit_item, list) or isinstance(audit_item, tuple):
      value_parts = []
      for audit_item_part in audit_item:
        value_parts.append(AuditItem.generate_audit_tree(audit_item_part))
      return value_parts
    elif isinstance(audit_item, AuditItem):
      key = audit_item.name
      value = AuditItem.generate_audit_tree(audit_item.value)
      return { key: value }
    else:
      return audit_item
