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

from gevent import spawn_later
from jinja2 import Template
import json
import os
import psutil

from tellapart.aurproxy.exception import AurProxyConfigException
from tellapart.aurproxy.source.source import ProxySource
from tellapart.aurproxy.util import (
  get_logger,
  load_klass_plugin)

logger = get_logger(__name__)

# Fallback for use when no valid gor command line possible.
_FALLBACK_MSG = 'No mirror source endpoints found.'
_FALLBACK_COMMAND_TEMPLATE = 'echo $$ > {{pid_path}} && exec python -c ' \
                             '"exec(\\"from gevent import sleep\\n' \
                             'while True:' \
                             ' print \'{{fallback_msg}}\';' \
                             ' sleep(10)\\")"'
_GOR_PATH = '/opt/go/bin/gor'
_GOR_COMMAND_PATH = '/etc/aurproxy/gor/dynamic.sh'

def load_mirror_updater(source,
                        ports,
                        max_qps,
                        max_update_frequency,
                        command_template_path,
                        pid_path):
  """
  Load a MirrorUpdater.

  Args:
    source - JSON string or ProxySource - Source whose endpoints describe gor
      repeaters.
    ports - string of comma seperated integers- Local ports to mirror.
      Example: "8080,8081"
    max_qps - integer - Max QPS to mirror to gor repeater.
    max_update_frequency - integer - number of seconds between updates of
      mirror configuration.
    command_template_path - str - path to command template to be rendered.

  Returns:
    A MirrorUpdater instance.
  """
  if not source:
    raise AurProxyConfigException('source_config required!')
  if not ports:
    raise AurProxyConfigException('ports required!')
  if not max_qps:
    raise AurProxyConfigException('max_qps required!')
  if not os.path.isfile(command_template_path):
    msg = '"{0}" doesn\'t exist!'.format(command_template_path)
    raise AurProxyConfigException(msg)
  ports = [ int(p) for p in ports.split(',') ]

  if not isinstance(source, ProxySource):
    source_dict = json.loads(source)
    source = load_klass_plugin(source_dict,
                               klass_field_name='source_class')

  return MirrorUpdater(source,
                       ports,
                       max_qps,
                       max_update_frequency,
                       command_template_path,
                       pid_path)

class MirrorUpdater(object):
  def __init__(self,
               source,
               ports,
               max_qps,
               max_update_frequency,
               command_template_path,
               pid_path,
               gor_path=_GOR_PATH,
               command_path=_GOR_COMMAND_PATH):
    """
    Manages updating the managed traffic mirroring process (gor).

    Args:
      source - aurproxy.source.ProxySource - Source whose endpoints describe
        gor repeaters.
      ports - list(int) - Local ports to mirror.
        Example: [8080, 8081]
      max_qps - integer - Max QPS to mirror to gor repeater.
      max_update_frequency - integer - number of seconds between updates of
        mirror configuration.
      command_template_path - str - path to command template to be rendered.
    """
    source.register_on_add(self._on_add)
    source.register_on_remove(self._on_remove)
    self._source = source
    self._ports = ports
    self._max_qps = max_qps
    self._max_update_frequency = max_update_frequency
    self._gor_path = gor_path
    self._pid_path = pid_path
    self._template_path = command_template_path
    self._command_path = command_path
    self._fallback_message = _FALLBACK_MSG
    self._fallback_command_template = _FALLBACK_COMMAND_TEMPLATE
    self._needs_update = True
    self._updating = False

  @property
  def blueprints(self):
    """
    Flask blueprints describing managed APIs.
    """
    if self._source.blueprint:
      return [self._source.blueprint]
    else:
      return []

  def set_up(self):
    """
    One-off way to generate mirroring process configuration (command).
    """
    self._source.start()
    self.update(kill_running=False)

  def start(self):
    """
    Start managing a mirroring process configuration (command).

    Long running.
    """
    self._source.start()
    spawn_later(self._max_update_frequency, self.update)

  def _on_add(self, source, endpoint):
    """
    Callback when mirror endpoint is added to source.

    Args:
      source - aurproxy.source.ProxySource - Unused.
      endpoint - aurproxy.config.endpoint.SourceEndpoint - Unused.

    Returns:
      Nothing
    """
    self._on_update()

  def _on_remove(self, source, endpoint):
    """
    Callback when mirror endpoint is removed from source.

    Args:
      source - aurproxy.source.ProxySource - Unused.
      endpoint - aurproxy.config.endpoint.SourceEndpoint - Unused.

    Returns:
      Nothing
    """
    self._on_update()

  def _on_update(self):
    """
    Signal that an update of mirroring process configuration is required.
    """
    self._needs_update = True

  def _should_update(self):
    """
    Determines whether an update can be applied.
    """
    return self._needs_update and not self._updating

  def update(self, kill_running=True):
    """
    Update the configuration of the traffic mirroring process (gor).

    Args:
      kill_running - boolean - whether to kill running mirroring processes.

    Returns:
      Nothing
    """
    try:
      if self._should_update():
        self._needs_update = False
        self._updating = True
        logger.info('Updating traffic mirror configuration.')

        command = self._generate_command()
        success = self._update(command, self._command_path, kill_running)
        if not success:
          logger.info('Failed to update! Rescheduling.')
          self._needs_update = True
    except Exception:
      self._needs_update = True
      logger.exception('Attempt to update traffic mirror configuration'
                       ' failed.')
    finally:
      self._updating = False
      spawn_later(self._max_update_frequency, self.update)

  def _generate_command(self):
    """
    Create command for injection into dynamic launch script.

    Returns:
      String command.
    """
    if not self._source.endpoints:
      # Aurora is going to keep the replay process running whether or not we
      # have the endpoints needed to construct a valid gor command. If we
      # don't, drop in a placeholder.
      template = self._fallback_command_template
      context = self._generate_fallback_context()
    else:
      with open(self._template_path) as t:
        template = t.read()
      context = self._generate_context()

    return self._render(template, context)

  def _generate_fallback_context(self):
    context = {}
    context['fallback_msg'] = self._fallback_message
    context['pid_path'] = self._pid_path
    return context

  def _generate_context(self):
    """
    Build context necessary to render gor command.

    Returns:
      Context dictionary.
    """
    context = {}
    context['gor_path'] = self._gor_path
    context['ports'] = self._ports
    context['endpoints'] = self._source.endpoints
    context['max_qps'] = self._max_qps
    context['pid_path'] = self._pid_path
    return context

  def _render(self, template, context):
    """
    Render gor command.

    Args:
      template_path - str - path to gor command template.
      context - dict - parameters to gor command template.

    Returns:
      Rendered gor command.
    """
    return Template(template).render(**context)

  def _update(self, command, command_path, kill_running):
    """
    Update mirroring process dynamic launch script.

    Args:
      command - str - traffic mirroring process command.
      command_path - path to process mirroring dynamic launch script.
      kill_running - boolean - whether to kill running mirroring processes.

    Returns:
      Boolean indicating whether update was successful.
    """
    updated = self._update_command(command, command_path)
    success = False
    if updated and kill_running:
      # Currently no graceful restart mechanism in gor
      # Depend on Aurora to start gor back up
      success = self._kill_running()
    return updated and success

  def _update_command(self, command, command_path):
    """
    Apply update of dynamic launch script.

    Args:
      command - str - traffic mirroring process command.
      command_path - path to process mirroring dynamic launch script.

    Returns:
      Boolean indicating whether update was applied.
    """
    updated = False
    # Don't rewrite it if nothing has changed.
    if os.path.isfile(command_path):
      with open(command_path) as cp:
        if cp.read() == command:
          logger.info('Mirror command is unchanged.')
          updated = True
          return updated

    logger.info('Writing new mirror command.')
    logger.info('Command: {0}'.format(command))
    try:
      with os.fdopen(os.open(command_path,
                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             0755), 'w') as command_handle:
        command_handle.write(command)
        updated = True
    except Exception:
      logger.exception('Attempt to update mirror command failed!')
    return updated

  def _kill_running(self):
    """
    Kill running traffic mirror and fallback processes.

    Returns:
      Whether successful in killing all traffic mirror and fallback processes.
    """
    logger.info('Looking for existing traffic mirror processes.')
    success = True
    killed_any = False
    try:
      proc = psutil.Process(self._get_pid())
      cmd_line = ' '.join(proc.cmdline())
      if self._gor_path in cmd_line \
        or _FALLBACK_MSG in cmd_line:
        msg = 'Killing traffic mirror process: {0}'.format(cmd_line)
        logger.info(msg)
        proc.kill()
      else:
        msg = 'Pid is for process with invalid cmd_line: {0}'.format(cmd_line)
        raise Exception(msg)
    except Exception:
      logger.exception('Attempt to kill traffic mirror processes failed!')
      success = False
    if not killed_any:
      logger.info('Did not kill any traffic mirror processes.')
    return success

  def _get_pid(self):
    pid_raw = None
    with open(self._pid_path) as pid_file:
      try:
        pid_raw = pid_file.read()
        pid = int(pid_raw)
        return pid
      except Exception:
        logger.error('Pid retrieval failed. Value: {0}'.format(pid_raw))
        raise
