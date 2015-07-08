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

import collections
import copy
from gevent import spawn_later
from gevent.event import Event
import requests

from tellapart.aurproxy.audit import AuditItem
from tellapart.aurproxy.share.adjuster import ShareAdjuster
from tellapart.aurproxy.util import get_logger


logger = get_logger(__name__)

class HttpHealthCheckLogEvent(object):
  """
  Events that can be logged during the course of HttpHealthCheck execution.
  """
  COMPLETED_CHECK = 'completed_check'
  RUNNING_CALLBACK = 'running_callback'
  RUNNING_CHECK = 'running_check'
  STARTED_CHECKER = 'started_checker'
  STARTING_CHECK = 'starting_check'
  STOPPED_CHECKER = 'stopped_checker'
  UPDATED_HEALTH_STATUS = 'updated_health_status'

class HttpHealthCheckLogResult(object):
  """
  Action results that can be logged during the course of HttpHealthCheck
  execution.
  """
  ERROR = 'error'
  FAILURE = 'failure'
  SUCCESS = 'success'
  TIMEOUT = 'timeout'

class HealthCheckResult(object):
  """
  Possible results of individual check runs.
  """
  ERROR_CODE = 'error_code'
  KNOWN_LOCAL_ERROR = 'known_local_error'
  KNOWN_REMOTE_ERROR = 'known_remote_error'
  SUCCESS = 'success'
  TIMEOUT = 'timeout'
  UNKNOWN_ERROR = 'unknown_error'

HEALTHY_RESULTS = [ HealthCheckResult.SUCCESS ]
UNCHANGED_RESULTS = [ HealthCheckResult.KNOWN_LOCAL_ERROR ]
UNHEALTHY_RESULTS = [ HealthCheckResult.ERROR_CODE,
                      HealthCheckResult.KNOWN_REMOTE_ERROR,
                      HealthCheckResult.TIMEOUT,
                      HealthCheckResult.UNKNOWN_ERROR ]

SUPPORTED_HEALTHCHECK_METHODS = ('GET', 'HEAD')


class HealthCheckStatus(object):
  """
  Possible statuses of ongoing check instances.
  """
  HEALTHY = 'healthy'
  INITIALIZING = 'initializing'
  UNHEALTHY = 'unhealthy'

HEALTHY_STATUSES = [ HealthCheckStatus.HEALTHY ]

class HttpHealthCheckShareAdjuster(ShareAdjuster):
  def __init__(self, endpoint, signal_update_fn, route='/health', interval=5,
               timeout=3.0, unhealthy_threshold=2, healthy_threshold=2,
               port_name=None, http_method='GET'):
    """
    A basic http health check implementation. Parameters match those available
    on an Elastic Loadbalancer.

    Checks for 200 response code.

    Args:
      endpoint - Endpoint to check.
      signal_update_fn - function - function to call on status update.
      route - str - http route to check.
      interval - int - seconds between checks.
      timeout - float - seconds before a check attempt times out.
      unhealthy_threshold - int - failures before endpoint marked unhealthy.
      healthy_threshold - int - successes before endpoint marked healthy.
      port_name - str - Optional name of port to check. EG: 'health'.
      http_method - str - Optional uppercase name of the http verb. EG: GET or HEAD
    """
    super(HttpHealthCheckShareAdjuster, self).__init__(endpoint,
                                                       signal_update_fn)
    self._route = route
    self._interval = int(interval)
    self._timeout = float(timeout)
    self._unhealthy_threshold = int(unhealthy_threshold)
    self._healthy_threshold = int(healthy_threshold)
    self._port_name = port_name
    max_result_len = self._healthy_threshold + self._unhealthy_threshold
    self._check_results = collections.deque(maxlen=max_result_len)
    self._status = HealthCheckStatus.INITIALIZING
    self._stop_event = Event()

    if http_method.upper() not in SUPPORTED_HEALTHCHECK_METHODS:
      raise Exception('http_method only supports: {}'.format(
        ', '.join(SUPPORTED_HEALTHCHECK_METHODS),
      ))
    self._http_method = http_method.lower()

  @property
  def status(self):
    """
    Get current status of endpoint.

    Returns:
      A HealthCheckStatus value.
    """
    return self._status

  def start(self):
    """
    Start running healthchecks against endpoint.
    """
    spawn_later(self._interval, self._check)
    self._record(HttpHealthCheckLogEvent.STARTED_CHECKER,
                 HttpHealthCheckLogResult.SUCCESS)

  def stop(self):
    """
    Stop running healthchecks against endpoint.
    """
    self._stop_event.set()
    self._record(HttpHealthCheckLogEvent.STOPPED_CHECKER,
                 HttpHealthCheckLogResult.SUCCESS)

  @property
  def auditable_share(self):
    """Return current share adjustment factor.
    """
    if self.status in HEALTHY_STATUSES:
      return 1.0, AuditItem('health', '1.0')
    else:
      return 0.0, AuditItem('health', '0.0')

  def _build_check_uri(self):
    """
    Builds the URI to check.

    Returns:
      Check URI string.
    """
    uri_template = 'http://{0}:{1}{2}'
    if self._port_name:
      port = self._endpoint.context['port_map'][self._port_name]
    else:
      port = self._endpoint.port
    return uri_template.format(self._endpoint.host,
                               port,
                               self._route)

  def _check(self):
    """
    Run healthcheck.

    Args:
      restart_timer - bool - Whether to restart check timer after checking.
    """
    if self._stop_event.is_set():
      return

    check_uri = self._build_check_uri()
    error_log_fn = None
    try:
      self._record(HttpHealthCheckLogEvent.STARTING_CHECK,
                   HttpHealthCheckLogResult.SUCCESS, log_fn=logger.debug)

      r = getattr(requests, self._http_method)(check_uri, timeout=self._timeout)

      if r.status_code == requests.codes.ok:
        check_result = HealthCheckResult.SUCCESS
        self._record(HttpHealthCheckLogEvent.RUNNING_CHECK,
                     HttpHealthCheckLogResult.SUCCESS, log_fn=logger.debug)
      else:
        check_result = HealthCheckResult.ERROR_CODE
        self._record(HttpHealthCheckLogEvent.RUNNING_CHECK,
                     HttpHealthCheckLogResult.FAILURE,
                     'status_code:{0}'.format(r.status_code))

    except requests.exceptions.Timeout:
      check_result = HealthCheckResult.TIMEOUT
      self._record(HttpHealthCheckLogEvent.RUNNING_CHECK,
                   HttpHealthCheckLogResult.TIMEOUT)
    except requests.exceptions.ConnectionError as ex:
      if 'gaierror' in unicode(ex):
        check_result = HealthCheckResult.KNOWN_LOCAL_ERROR
        error_log_fn = logger.error
      elif 'Connection Refused' in unicode(ex):
        check_result = HealthCheckResult.KNOWN_REMOTE_ERROR
        error_log_fn = logger.error
      else:
        check_result = HealthCheckResult.UNKNOWN_ERROR
        error_log_fn = logger.exception
    except Exception:
      check_result = HealthCheckResult.UNKNOWN_ERROR
      error_log_fn = logger.exception

    if error_log_fn:
      error_log_fn('Exception when executing HttpHealthCheck.')
      self._record(HttpHealthCheckLogEvent.RUNNING_CHECK,
                   check_result)

    self._update_status(check_result)
    spawn_later(self._interval, self._check)

  def _record(self, event, result, msg='', log_fn=logger.info):
    """
    Utility to record HttpHealthCheck events and results.

    Args:
      event - HttpHealthCheckLogEvent.
      result - HttpHealthCheckLogResult.
      msg - str - Extra message.
      log_fn - function - logger function to use.
    """
    f = 'event:%(event)s result:%(result)s check_uri:%(check_uri)s msg:%(msg)s'
    context = { 'event': event,
                'result': result,
                'check_uri': self._build_check_uri(),
                'msg': msg }
    log_fn(f, context)

  def _update_status(self, check_result):
    """
    If necessary based on configuration, update status of this check.

    Calls self._callback if set.

    Args:
      check_result - HttpCheckResult
    """
    if check_result in UNCHANGED_RESULTS:
      return

    self._check_results.append(check_result)
    check_results = copy.copy(self._check_results)
    calculated_status = self._status
    healthy_lookback = list(check_results)[-self._healthy_threshold:]
    if len(healthy_lookback) == self._healthy_threshold and \
        all([cr in HEALTHY_RESULTS for cr in healthy_lookback]):
      calculated_status = HealthCheckStatus.HEALTHY

    unhealthy_lookback = list(check_results)[-self._unhealthy_threshold:]
    if len(unhealthy_lookback) == self._unhealthy_threshold and \
        all([cr in UNHEALTHY_RESULTS for cr in unhealthy_lookback]):
      calculated_status = HealthCheckStatus.UNHEALTHY

    if self._status != calculated_status:
      old_status = self._status
      self._status = calculated_status
      self._record(HttpHealthCheckLogEvent.UPDATED_HEALTH_STATUS,
                   HttpHealthCheckLogResult.SUCCESS,
                   '{0} -> {1}'.format(old_status, calculated_status))
      if self._signal_update_fn:
        try:
          # Execute callback, passing old and new status
          self._signal_update_fn()
        except Exception:
          logger.exception('Exception when executing callback on '
                           'BasicHttpHealthCheck status change.')
          self._record(HttpHealthCheckLogEvent.RUNNING_CALLBACK,
                       HttpHealthCheckLogResult.ERROR)
