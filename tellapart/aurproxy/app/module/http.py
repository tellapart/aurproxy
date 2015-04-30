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

"""Basic Flask HTTP modules for composing larger applications.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from flask import (
  Blueprint,
  Response)
from flask.ext import restful

from tellapart.aurproxy.app import lifecycle
from tellapart.aurproxy.metrics.store import root_metric_store

# Define a standard blueprint for lifecycle management endpoints
lifecycle_blueprint = Blueprint('lifecycle', __name__)
_bp = restful.Api(lifecycle_blueprint)

@_bp.resource('/quitquitquit')
class QuitQuitQuit(restful.Resource):
  def post(self):
    lifecycle.execute_shutdown_handlers()
    return 'OK', 200

@_bp.resource('/abortabortabort')
class AbortAbortAbort(restful.Resource):
  def post(self):
    lifecycle.execute_shutdown_handlers()
    return 'OK', 200

@_bp.resource('/health')
class Health(restful.Resource):
  def get(self):
    status, message = lifecycle.check_health()
    if not status:
      # Still respond with 200, otherwise Aurora UI doesn't show failure text.
      return Response(response='Health checks failed: %s' % message)

    return Response(response='OK')

@_bp.resource('/metrics')
class Metrics(restful.Resource):
  def get(self):
    metrics = root_metric_store().get_metrics()
    ordered_metrics = sorted(metrics, key=lambda metric: metric.name)

    joined = '\n'.join(['%s %s' % (m.name, m.value()) for m in ordered_metrics])
    return Response(response=joined)

@_bp.resource('/metrics.json')
class MetricsJson(restful.Resource):
  def get(self):
    metrics = root_metric_store().get_metrics()
    ordered_metrics = sorted(metrics, key=lambda metric: metric.name)

    return dict((m.name, m.value()) for m in ordered_metrics)
