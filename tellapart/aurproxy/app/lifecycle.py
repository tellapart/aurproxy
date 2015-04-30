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

"""Basic application lifecycle functionality.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from tellapart.aurproxy.exception import AurProxyValueException
from tellapart.aurproxy.metrics.store import root_metric_store
from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

_SHUTDOWN_HANDLERS = []
_HEALTHCHECK_HANDLERS = []

def register_shutdown_handler(handler):
  """Registers a callable to be executed at application shutdown.

  Args:
    handler - Callable to be executed at application shutdown.
  """
  if not callable(handler):
    raise AurProxyValueException('Handler must be callable.')

  _SHUTDOWN_HANDLERS.append(handler)

def register_healthcheck_handler(handler):
  """Registers a callable to be executed when application health is queried. The
  callable should return a tuple of (success, message).

  Args:
    handler - Callable to be executed when application health is queried.
  """
  if not callable(handler):
    raise AurProxyValueException('Handler must be callable.')

  _HEALTHCHECK_HANDLERS.append(handler)

def execute_shutdown_handlers():
  """Gracefully terminates the running application by running shutdown handlers.
  """
  logger.info('Executing shutdown handlers.')
  while _SHUTDOWN_HANDLERS:
    handler = _SHUTDOWN_HANDLERS.pop() #  Make sure we only run once.
    handler()

  logger.info('Flushing metrics.')
  root_metric_store().flush_all_publishers()

def check_health():
  """Executes all registered health check handlers.

  Returns:
    A tuple of (success, message).
  """
  logger.info('Executing health check handlers.')
  for handler in _HEALTHCHECK_HANDLERS:
    result, message = handler()
    if not result:
      return result, message

  return True, 'OK'
