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

import re
import copy
import logging
import importlib
import subprocess
import unicodedata
from hashlib import md5
from collections import namedtuple

import gevent
import gevent.event
from raven import Client
from raven.conf import setup_logging
from raven.handlers.logging import SentryHandler
from raven.middleware import Sentry


_CLASS_PATH_TO_CLASS_CACHE = {}


CommandResult = namedtuple('CommandResult', 'returncode', 'stdout', 'stderr')


def class_from_class_path(class_path):
  """
  Get a python class instance given the python "class path".
  EG:
  # >>> class_from_class_path("decimal.Decimal")
  #    <class 'decimal.Decimal'>

  Args:
      class_path - str - dot-delimited python path followed by class name.

  Returns:
      class instance pointed to by "class path"
  """
  if class_path not in _CLASS_PATH_TO_CLASS_CACHE:
    module_name, class_name = class_path.rsplit('.', 1)
    m = importlib.import_module(module_name)
    c = getattr(m, class_name)
    _CLASS_PATH_TO_CLASS_CACHE[class_path] = c

  return _CLASS_PATH_TO_CLASS_CACHE[class_path]

def get_logger(name):
  log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  logging.basicConfig(level=logging.INFO, format=log_format)
  logger = logging.getLogger(name)
  return logger

class KlassFactory(object):
  def __init__(self, klass, **kwargs):
    self._klass = klass
    self._kwargs = kwargs

  def build(self, **extra_kwargs):
    kwargs = dict(self._kwargs.items() + extra_kwargs.items())
    return load_plugin(self._klass, **kwargs)

def load_plugin(plugin_class_path, **plugin_kwargs):
  """
  Load a and instantiate a plugin.

  Args:
      plugin_class_path - str - python class path. EG: 'decimal.Decimal'
      plugin_kwargs - list(str) - list of "=" delimited key value pairs.
                                  EG: ["value=1"]
  Returns:
      An instantiated plugin.
  """
  plugin_class = class_from_class_path(plugin_class_path)
  plugin = plugin_class(**plugin_kwargs)
  return plugin

def load_cli_kwargs(kwargs_list, delimiter='='):
  """
  Parse a list of command line interface "kwargs".

  ["key1=val1", "key2=val2"] -> {"key1": "val1", "key2": "val2"}
  (Where "=" is the passed delimiter value.)

  Args:
    kwargs_list - list(str) - list of delimited key value pairs.
    delimiter - str - value on which to split kwargs_list items.

  Returns:
    A kwarg-populated dictionary.
  """
  kwargs = {}
  for kv in kwargs_list:
    k, v = kv.split(delimiter, 1)
    kwargs[k] = v
  return kwargs

def load_cli_plugin(klass, cli_kwargs, extra_kwargs=None):
  kwargs = load_cli_kwargs(cli_kwargs)
  if extra_kwargs:
    kwargs = dict(kwargs.items() + extra_kwargs.items())
  return load_plugin(klass, **kwargs)

def load_registration_plugin(registration_class, *registration_kwargs):
  registration_kwargs = load_cli_kwargs(registration_kwargs)
  return load_plugin(registration_class, **registration_kwargs)

def load_klass_factory(klass, **kwargs):
  return KlassFactory(klass, **kwargs)

def load_klass_plugin(klass_dict,
                      klass_field_name='klass',
                      **extra_kwargs):
  klass_dict_copy = copy.deepcopy(klass_dict)
  klass = klass_dict_copy.pop(klass_field_name)
  kwargs = klass_dict_copy
  kwargs = dict(kwargs.items() + extra_kwargs.items())
  return load_plugin(klass, **kwargs)

def slugify(s):
  slug = unicodedata.normalize('NFKD', unicode(s))
  slug = slug.encode('ascii', 'ignore').lower()
  slug = re.sub(r'[^a-z0-9]+', '_', slug).strip('_')

  # To avoid slug collision, append hash of raw string
  m = md5()
  m.update(s.encode('utf8'))
  slug = '{0}_{1}'.format(slug, m.hexdigest())

  return slug


def run_local(command, capture=False):
  proc = subprocess.Popen(
    command,
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )
  stdout, stderr = proc.communicate()

  if capture:
    return CommandResult(
      returncode=proc.returncode,
      stdout=stdout,
      stderr=stderr,
    )


def setup_sentry(dsn=None):
  """Configures the Sentry logging handler.

  Args:
    dsn - DSN for the Sentry project.
  """
  handler = SentryHandler(dsn, level=logging.ERROR)
  setup_logging(handler)

def setup_sentry_wsgi(app, dsn):
  return Sentry(app, Client(dsn))

class PeriodicTask(object):
  """Class that will run a target function periodically.
  """

  def __init__(self, period, fn):
    """
    Args:
      period - Interval in seconds to wait between executions.
      fn - The function to call.
    """
    self._period = float(period)
    self._fn = fn
    self._stop_event = gevent.event.Event()

  def start(self):
    """Override of base method.
    """
    gevent.spawn_later(self._period, self._run)

  def stop(self):
    """Signals task to stop.
    """
    self._stop_event.set()

  def _run(self):
    if not self._stop_event.isSet():
      try:
        self._fn()
      except Exception:
        logger = get_logger(unicode(self._fn))
        logger.exception("Failed to execute PeriodicTask.")
      finally:
        gevent.spawn_later(self._period, self._run)
