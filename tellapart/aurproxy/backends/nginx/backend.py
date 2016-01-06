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

from jinja2 import Template
import os

from tellapart.aurproxy.backends import ProxyBackend
from tellapart.aurproxy.backends.nginx.metrics import \
  NginxProxyMetricsPublisher
from tellapart.aurproxy.metrics.store import increment_counter
from tellapart.aurproxy.util import (
  get_logger,
  move_file,
  run_local)

logger = get_logger(__name__)

_DEFAULT_CONFIG_DEST = '/etc/aurproxy/nginx/nginx.conf'
_DEFAULT_TEMPLATE_LOC = './tellapart/aurproxy/templates/' \
                        'nginx/nginx.conf.template'

_METRIC_UPDATE_SUCCEEDED = 'update_succeeded'
_METRIC_UPDATE_FAILED = 'update_failed'

_METRIC_REVERT_SUCCEEDED = 'revert_succeeded'
_METRIC_REVERT_FAILED = 'revert_failed'

class NginxProxyBackend(ProxyBackend):
  NAME = 'nginx'

  def __init__(self, configuration, signal_update_fn):
    super(NginxProxyBackend, self).__init__(configuration, signal_update_fn)
    config = self._configuration
    template = self._load_config_item('template_file',
                                      config,
                                      default=_DEFAULT_TEMPLATE_LOC,
                                      required=False)
    self._config_file_template = template
    destination = self._load_config_item('configuration_file',
                                         config,
                                         default=_DEFAULT_CONFIG_DEST,
                                         required=False)
    self._config_file_destination = destination
    self._stats_port = self._load_config_item('stats_port',
                                              config,
                                              default=None,
                                              required=False)
    self._nginx_pid_path = self._load_config_item('nginx_pid_path',
                                              config,
                                              default='/var/run/nginx.pid',
                                              required=False)
    if self._stats_port:
      self._metrics_publisher = NginxProxyMetricsPublisher(self._stats_port)
    else:
      self._metrics_publisher = None

  @property
  def metrics_publisher(self):
    """Returns a metric publisher if the stats_port is specified in the config.

    Returns:
      A ProxyMetricsPublisher object.
    """
    return self._metrics_publisher

  def _generate_context(self):

    context = {'context': self._context,
               'stats_port': self._stats_port,
               'nginx_pid_path': self._nginx_pid_path}

    context['http_servers'] = []
    context['stream_servers'] = []

    for proxy_server in self._proxy_servers:
      if proxy_server.routes and not proxy_server.streams:
        context['http_servers'].append(proxy_server)
      elif proxy_server.streams and not proxy_server.routes:
        context['stream_servers'].append(proxy_server)
      else:
        raise Exception('Invalid configuration - '
                        'ProxyServer can have routes or streams but not both.')
    return context

  def restart(self):
    run_local('kill -HUP $( cat {0} )'.format(self._nginx_pid_path))

  def update(self, restart_proxy):
    context = self._generate_context()
    config = self._render(self._config_file_template, context)
    success = self._update(config,
                           self._config_file_destination,
                           restart_proxy=restart_proxy)
    if not success:
      logger.info('Failed to update! Rescheduling.')
      self.signal_update()

  def _render(self, template_loc, context):
    with open(template_loc) as t:
      template = Template(t.read())
    return template.render(**context)

  def _update(self, config, config_dest, restart_proxy):
    if not self._should_update_config(config, config_dest):
      logger.info('No update required.')
      return True

    self._backup(config_dest)
    revert = False
    try:
      logger.info('Writing new configuration.')
      logger.info(config)
      with open(config_dest, 'w') as updated_config:
        updated_config.write(config)

      increment_counter(_METRIC_UPDATE_SUCCEEDED)
      if restart_proxy:
        logger.info('Applying new configuration.')
        self.restart()
    except Exception:
      logger.exception('Writing new configuration failed.')
      revert = True
    finally:
      if revert:
        logger.error('Validation of new configuration failed!')
        logger.warning('Reverting to %s', self._build_backup_path(config_dest))
        try:
          self._revert(config_dest)
          increment_counter(_METRIC_REVERT_SUCCEEDED)
        except Exception:
          logger.exception('Attempt to revert to old configuration failed!')
          increment_counter(_METRIC_REVERT_FAILED)
    return not revert

  def _should_update_config(self, new_config, config_dest):
    try:
      with open(config_dest) as current_file:
        current_config = current_file.read()
        return new_config != current_config
    except IOError:
      return True

  def _build_backup_path(self, config_dest):
    return '{0}.1'.format(config_dest)

  def _backup(self, config_dest):
    if os.path.isfile(config_dest):
      backup_path = self._build_backup_path(config_dest)
      move_file(config_dest, backup_path)

  def _revert(self, config_dest):
    backup_path = self._build_backup_path(config_dest)
    if os.path.isfile(backup_path):
      move_file(backup_path, config_dest)
