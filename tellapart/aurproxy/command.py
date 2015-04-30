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
from tellapart.aurproxy.proxy import ProxyUpdater
from tellapart.aurproxy.util import (
  get_logger,
  load_cli_plugin,
  load_klass_plugin,
  setup_sentry,
  setup_sentry_wsgi)


logger = get_logger(__name__)
logging.getLogger('requests').setLevel(logging.WARNING)

_DEFAULT_BACKEND = 'nginx'
_DEFAULT_MAX_UPDATE_FREQUENCY = 10
_DEFAULT_METRIC_PUBLISHER_CLASS = None
_DEFAULT_METRIC_PUBLISHER_KWARGS = []
_DEFAULT_REGISTRATION_CLASS = None
_DEFAULT_REGISTRATION_KWARGS = []
_DEFAULT_UPDATE_PERIOD = 2
_DEFAULT_WEIGHT_ADJUSTMENT_DELAY_SEC = 180

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
        sentry_dsn=None,
        setup=False):
  """Run the Aurproxy load balancer manager.

  Args:
    management_port - int - port for the manager application to listen on for
      Aurora lifecycle queries and events (/health, /quitquit, etc.).
    config - JSON String - Load balancer configuration. See README.md for
      detailed documentation.
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
  proxy_config = json.loads(config)

  # Set up updater
  proxy_updater = ProxyUpdater(backend, proxy_config, update_period,
                               max_update_frequency)

  if setup:
    proxy_updater.set_up()
  else:
    # Set up metrics
    set_root_prefix('aurproxy')
    if metric_publisher_class:
      try:
        publisher = load_cli_plugin(metric_publisher_class,
                                    metric_publisher_arg)
        add_publisher(publisher)
      except Exception:
        logger.exception('Metrics failure.')
        raise

    # Set up registration
    if registration_class:
      try:
        registerer = load_cli_plugin(registration_class, registration_arg)
        registerer.add()
        register_shutdown_handler(registerer.remove)
      except Exception:
        logger.exception('Registration failure.')
        raise

    # Start the proxy updater.
    proxy_updater.start(weight_adjustment_delay_seconds)

    # Set up management application
    app = Flask(__name__)
    app.register_blueprint(lifecycle_blueprint)
    if sentry_dsn:
      app = setup_sentry_wsgi(app, sentry_dsn)
    http_server = WSGIServer(('0.0.0.0', int(management_port)), app)
    http_server.serve_forever()

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
  source_dict = json.loads(registration_source)
  source = load_klass_plugin(source_dict,
                             klass_field_name='source_class')
  extra_kwargs = {'source': source}
  registerer = load_cli_plugin(registration_class,
                               registration_arg,
                               extra_kwargs=extra_kwargs)
  registerer.synchronize(write)

if __name__ == '__main__':
  commandr.Run()
