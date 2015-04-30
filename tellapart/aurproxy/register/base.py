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

"""Base classes for registration.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

_TRUISH = ['true', 'True', True]

class RegistrationAction(object):
  NONE = 'none'
  REGISTER = 'register'
  REMOVE = 'remove'

class RegistrationActionReason(object):
  ALREADY_REGISTERED = 'already_registered'
  NO_CORRESPONDING_TASK = 'no_corresponding_task'
  NO_REASON = 'no_reason'
  NOT_ALREADY_REGISTERED = 'not_already_registered'
  NOT_YET_REGISTERED = 'not_yet_registered'
  REMOVE_OTHER_INSTANCE_FALSE = 'remove_other_instances_false'

class BaseRegisterer(object):

  def add(self):
    raise NotImplementedError('add')

  def remove(self):
    raise NotImplementedError('remove')

  def synchronize(self, write):
    raise NotImplementedError('synchronize')

  def record(self, resource_name, instance_id, action, reasons='', msg='',
             log_fn=logger.info):
    """
    Record actions taken for logs and metrics.

    Args:
      resource_name - str - Resource name.
      instance_id - str - Instance identifier (AWS instance id, DNS, etc.)
      action - str - Action taken (see RegistrationAction).
      reasons - list(str) - List of reasons for action (see
                            RegistrationActionReason).
      msg - str - Extra message to include.
      log_fn - Logger method to use.
    """
    if isinstance(reasons, basestring):
      reasons = [reasons]

    reasons = ','.join(reasons) if reasons else ''

    context = {'resource': resource_name,
               'instance': instance_id,
               'action': action,
               'reasons': reasons,
               'msg': msg}
    fmt = 'resource:%(resource)-12s instance:%(instance)-12s ' \
          'action:%(action)-10s reasons:%(reasons)-30s msg:%(msg)-15s'
    log_fn(fmt, context)

  def get_job_hosts(self, source):
    """
    Get the list of hosts for the configured aurproxy job.

    Args:
      source - ProxySource that can be used to retrieve job hosts.
    Returns:
      A list of EC2 host strings.
    """
    source.start()
    return [s.host for s in source.endpoints]

  def is_truish(self, value):
    """Attempts to coerce a "truish" result from value.

    Args:
      value - A string, boolean, etc. to be tested.

    Returns:
      A boolean.
    """
    return value in _TRUISH

class NoOpRegisterer(BaseRegisterer):

  def __init__(self, *args, **kwargs):
    pass

  def add(self):
    pass

  def remove(self):
    pass

  def synchronize(self, write):
    pass
