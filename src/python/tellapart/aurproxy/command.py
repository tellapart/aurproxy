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

import gevent.monkey
gevent.monkey.patch_all()

import commandr
from flask import Flask
from gevent.wsgi import WSGIServer
import json
import logging

from tellapart.aurproxy.app.module.http import lifecycle_blueprint
from tellapart.aurproxy.app.lifecycle import register_shutdown_handler
from tellapart.aurproxy.metrics.store import (
  add_publisher,
  set_root_prefix)
from tellapart.aurproxy.mirror import load_mirror_updater
from tellapart.aurproxy.proxy import ProxyUpdater
from tellapart.aurproxy.util import (
  get_logger,
  load_cli_plugin,
  load_klass_plugin,
  setup_sentry,
  setup_sentry_wsgi)

from tellapart.aurproxy.exception import AurProxyConfigException


logger = get_logger(__name__)
logging.getLogger('requests').setLevel(logging.WARNING)

_DEFAULT_BACKEND = 'nginx'
_DEFAULT_MAX_UPDATE_FREQUENCY = 10
_DEFAULT_METRIC_PUBLISHER_CLASS = None
_DEFAULT_METRIC_PUBLISHER_KWARGS = []
_DEFAULT_MIRROR_MAX_QPS = 0
_DEFAULT_MIRROR_MAX_UPDATE_FREQUENCY = 15
_DEFAULT_MIRROR_PORTS = None
_DEFAULT_MIRROR_SOURCE = None
_DEFAULT_REGISTRATION_CLASS = None
_DEFAULT_REGISTRATION_KWARGS = []
_DEFAULT_REPLAY_MAX_UPDATE_FREQUENCY = _DEFAULT_MIRROR_MAX_UPDATE_FREQUENCY

_DEFAULT_UPDATE_PERIOD = 2
_DEFAULT_WEIGHT_ADJUSTMENT_DELAY_SEC = 180

_MIRROR_COMMAND_TEMPLATE_PATH = './tellapart/aurproxy/templates/gor' \
                                '/mirror.sh.template'
_REPLAY_COMMAND_TEMPLATE_PATH = './tellapart/aurproxy/templates/gor' \
                                '/replay.sh.template'
_MIRROR_PID_PATH = '/tmp/mirror_pid'

@commandr.command
def run(management_port,
        config,
        backend=_DEFAULT_BACKEND,
        update_period=_DEFAULT_UPDATE_PERIOD,
        max_update_frequency=_DEFAULT_MAX_UPDATE_FREQUENCY,
        weight_adjustment_delay_seconds=_DEFAULT_WEIGHT_ADJUSTMENT_DELAY_SEC,
        registration_class=_DEFAULT_REGISTRATION_CLASS,
        registration_arg=_DEFAULT_REGISTRATION_KWARGS,
        metric_publisher_class=_DEFAULT_METRIC_PUBLISHER_CLASS,
        metric_publisher_arg=_DEFAULT_METRIC_PUBLISHER_KWARGS,
        mirror_source=_DEFAULT_MIRROR_SOURCE,
        mirror_ports=_DEFAULT_MIRROR_PORTS,
        mirror_max_qps=_DEFAULT_MIRROR_MAX_QPS,
        mirror_max_update_frequency=_DEFAULT_MIRROR_MAX_UPDATE_FREQUENCY,
        mirror_pid_path=_MIRROR_PID_PATH,
        sentry_dsn=None,
        setup=False):
  """Run the Aurproxy load balancer manager.

  Args:
    management_port - int - port for the manager application to listen on for
      Aurora lifecycle queries and events (/health, /quitquit, etc.).
    config - JSON String or file:// location of a JSON document - Load balancer
      configuration. See README.md for detailed documentation.
    backend - Load balancer manager backend to use. EG: "nginx".
    update_period - int - frequency with which the need to update is checked.
    max_update_frequency - int - minimum number of seconds between updates.
    weight_adjustment_delay_seconds - int - number of seconds to wait before
      starting configured share adjusters. May not want them running
      immediately after aurproxy deploys.
    registration_class - str - Python class path for registration class.
    registration_arg - list(str) - List of equal-sign-delimited string kwarg
      pairs.
      Example:
        ["domain=myapp.mydomain.com", "type=A"]
    metric_publisher_class - str - Python class path for metrics publisher
      class.
    metric_publisher_arg - list(str) - List of equal-sign-delimited string
      kwarg pairs.
      Example:
        ["source=cluster.role.environment.job"]
    mirror_source - JSON String - Source configuration for gor repeater to
      which http traffic should be mirrored.
    mirror_ports - Comma separated integer string - Local ports to mirror.
      Example: "8080,8081"
    mirror_max_qps - Max QPS to mirror to gor repeater.
    mirror_max_update_frequency - integer - number of seconds between updates
      of mirror configuration.
    sentry_dsn - str - Sentry DSN for error logging.
    setup - bool - When run in setup mode, aurproxy will render a configuration
     for the managed load balancer once and then exit. Run aurproxy once in
     setup mode to set up the load balancer, then start aurproxy and the load
     balancer together.
  """
  # Set up sentry error logging
  if sentry_dsn:
    setup_sentry(sentry_dsn)

  # Load config
  try:
    if config.startswith('file://'):
      with open(config.split('file://', 1)[1]) as config_fh:
        proxy_config = json.load(config_fh)
    else:
      proxy_config = json.loads(config)
  except (TypeError, ValueError):
    raise commandr.CommandrUsageError('Invalid JSON configuration specified via --config')
  except IOError as err:
    raise commandr.CommandrUsageError('Failed to read --config file: %s' % err)

  # Set up updater
  try:
    proxy_updater = ProxyUpdater(backend, proxy_config, update_period,
                                 max_update_frequency)
  except AurProxyConfigException as exc:
    raise commandr.CommandrUsageError(
      'Invalid configuration: {}'.format(str(exc)),
    )

  # Set up mirroring
  mirror_updater = None
  if mirror_source:
    mirror_updater = load_mirror_updater(mirror_source,
                                         mirror_ports,
                                         mirror_max_qps,
                                         mirror_max_update_frequency,
                                         _MIRROR_COMMAND_TEMPLATE_PATH,
                                         mirror_pid_path)

  if setup:
    proxy_updater.set_up()
    if mirror_updater:
      mirror_updater.set_up()
  else:
    # Set up metrics
    set_root_prefix('aurproxy')
    if metric_publisher_class:
      _setup_metrics(metric_publisher_class, metric_publisher_arg)

    # Set up registration
    if registration_class:
      try:
        registerer = load_cli_plugin(registration_class, registration_arg)
        registerer.add()
        register_shutdown_handler(registerer.remove)
      except Exception:
        logger.exception('Registration failure.')
        raise

    # Start the updaters and extract blueprints
    proxy_updater.start(weight_adjustment_delay_seconds)
    blueprints = proxy_updater.blueprints
    if mirror_updater:
      mirror_updater.start()
      blueprints += mirror_updater.blueprints

    _start_web(management_port, sentry_dsn, blueprints)

@commandr.command
def run_replay(management_port,
               replay_port,
               replay_source,
               replay_max_qps,
               replay_max_update_frequency=_DEFAULT_REPLAY_MAX_UPDATE_FREQUENCY,
               replay_pid_path=_MIRROR_PID_PATH,
               metric_publisher_class=_DEFAULT_METRIC_PUBLISHER_CLASS,
               metric_publisher_arg=_DEFAULT_METRIC_PUBLISHER_KWARGS,
               sentry_dsn=None,
               setup=False):
  """Run the Aurproxy traffic replay server manager.

  Args:
    management_port - int - port for the manager application to listen on for
      Aurora lifecycle queries and events (/health, /quitquit, etc.).
    replay_port - int - port on which the replay server to listen on for a
      mirrored traffic stream.
    replay_source - JSON string - Source configuration to which gor replay
      server will send traffic.
    replay_max_qps - maximum QPS to replay to listeners.
    replay_max_update_frequency - Max QPS to replay to source endpoints.
    metric_publisher_class - str - Python class path for metrics publisher
      class.
    metric_publisher_arg - list(str) - List of equal-sign-delimited string
      kwarg pairs.
      Example:
        ["source=cluster.role.environment.job"]
    sentry_dsn - str - Sentry DSN for error logging.
    setup - bool - When run in setup mode, aurproxy will render a configuration
      for the replay server once and then exit. Run aurproxy once in setup mode
      to set up the replay server, then start aurproxy and the replay server
      together.
  """
  try:
    source_dict = json.loads(replay_source)
  except (TypeError, ValueError):
    raise commandr.CommandrUsageError('Invalid JSON configuration specified via --replay_source')

  source = load_klass_plugin(source_dict, klass_field_name='source_class')
  mirror_updater = load_mirror_updater(source,
                                       replay_port,
                                       replay_max_qps,
                                       replay_max_update_frequency,
                                       _REPLAY_COMMAND_TEMPLATE_PATH,
                                       replay_pid_path)
  if setup:
    mirror_updater.update(kill_running=False)
  else:
    if metric_publisher_class:
      _setup_metrics(metric_publisher_class, metric_publisher_arg)
    mirror_updater.start()
    _start_web(management_port, sentry_dsn, mirror_updater.blueprints)

@commandr.command
def synchronize(registration_source,
                registration_class,
                registration_arg=_DEFAULT_REGISTRATION_KWARGS,
                write=False):
  """Add and remove Aurproxy task instances from upstream services.

  Intended to be run by administrators or to be called automatically as a cron
  as a supplement to / safety net for the pluggable in-task registration and
  deregistration Aurproxy events that are driven by Aurora lifecycle events.

  Args:
    registration_source - JSON string - Source configuration.
      Format:
        {'registration_class': 'python.class.path',
         'arg1': 'val1',
         'arg2': 'val2'}
      Example:
        '{"source_class": "aurproxy.sources.AuroraSource"
          "announcer_serverset_path": "/aurora/",
          "zk_servers": "0.zk.mycluster.mydomain.com:2181,
                         1.zk.mycluster.mydomain.com:2181,
                         2.zk.mycluster.mydomain.com:2181,
          "environment": "devel",
          "job": "proxytest",
          "role": "proxy",
          "endpoint": "http"}
      See source class definition for valid kwargs.
    registration_class - str - Python class path for registration class.
    registration_arg - list(str) - List of equal-sign-delimited string kwarg
      pairs.
      Example:
        ["domain=myapp.mydomain.com", "type=A"]
    write - bool - Whether to apply the changes.
  """
  try:
    source_dict = json.loads(registration_source)
  except (TypeError, ValueError):
    raise commandr.CommandrUsageError(
      'Invalid JSON configuration specified via --registration_source',
    )

  source = load_klass_plugin(source_dict,
                             klass_field_name='source_class')
  extra_kwargs = {'source': source}
  registerer = load_cli_plugin(registration_class,
                               registration_arg,
                               extra_kwargs=extra_kwargs)
  registerer.synchronize(write)

def _setup_metrics(metric_publisher_class, metric_publisher_args):
  """
  Sets up a metrics publisher based on command line args.

  Args:
    metric_publisher_class
    metric_publisher_args
  """
  try:
    publisher = load_cli_plugin(metric_publisher_class,
                                metric_publisher_args)
    add_publisher(publisher)
  except Exception:
    logger.exception('Metrics failure.')
    raise

def _start_web(port, sentry_dsn=None, blueprints=None):
  """
  Starts a Flask app with optional error logging and blueprint registration.

  Args:
    port - str/int - port on which management application should listen for
      HTTP traffic.
    sentry_dsn - str - Sentry DSN for error logging.
    blueprints - list(flask.Blueprint)- blueprints to register.
  """
  # Set up management application
  app = Flask(__name__)
  app.register_blueprint(lifecycle_blueprint)
  if blueprints:
    for blueprint in blueprints:
      app.register_blueprint(blueprint)
  if sentry_dsn:
    app = setup_sentry_wsgi(app, sentry_dsn)
  http_server = WSGIServer(('0.0.0.0', int(port)), app)
  http_server.serve_forever()

if __name__ == '__main__':
  try:
    commandr.Run()
  except KeyboardInterrupt:
    raise SystemExit('\nExiting on CTRL-c')
