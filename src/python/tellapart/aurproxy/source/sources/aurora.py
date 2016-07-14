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

from __future__ import absolute_import

from .serverset import ServerSetSource

_DEFAULT_ANNOUNCER_SERVERSET_PATH = '/aurora/'


def get_service_discovery_path(job, announcer_serverset_path):
  return '/{0}/{1}'.format(announcer_serverset_path, job)


def get_job_path(role, environment, job):
  return '{0}/{1}/{2}'.format(role, environment, job)


class AuroraProxySource(ServerSetSource):

  def __init__(self,
               role,
               environment,
               job,
               zk_servers,
               announcer_serverset_path=_DEFAULT_ANNOUNCER_SERVERSET_PATH,
               **kw):
  
    serverset_path = get_service_discovery_path(
        get_job_path(role, environment, job),
        announcer_serverset_path
    )
    super(AuroraProxySource, self).__init__(serverset_path, zk_servers, **kw)
