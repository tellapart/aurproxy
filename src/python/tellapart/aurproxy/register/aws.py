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

"""Base class and other utility methods for registration in AWS.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

import boto.ec2
import boto.ec2.elb
import boto.route53
import requests

from tellapart.aurproxy.register.base import BaseRegisterer

_CONN_MGR = None
_AWS_METADATA_URI = 'http://169.254.169.254/latest/meta-data/{0}'

class AwsRegisterer(BaseRegisterer):
  """Common code for AWS Registerers.
  """
  def __init__(self, region, access_key=None, secret_key=None):
    """
    Args:
      region - str - AWS region (EG: 'us-east-1').
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
    """
    self._region = region
    self._access_key = access_key
    self._secret_key = secret_key

  @property
  def conn(self):
    """
    Manages access to global BotoConnectionManager.

    Returns:
      BotoConnectionManager
    """
    global _CONN_MGR
    if not _CONN_MGR:
      _CONN_MGR = BotoConnectionManager(self._region,
                                        self._access_key,
                                        self._secret_key)
    return _CONN_MGR

  def get_current_instance_id(self):
    """Retrieves the EC2 instance id of the current machine.

    Returns:
      An EC2 instance id.
    """
    return self._get_instance_metadata('instance-id')

  def get_public_hostname(self):
    """Retrieves public hostname the current machine.

    Returns:
      A string representing a public DNS address.
    """
    return self._get_instance_metadata('public-hostname')

  def _get_instance_metadata(self, identifier):
    """Gets a specific piece of instance metadata from the local AWS instance.

    Args:
      identifier - The identifier of the metadata.

    Returns:
      The value corresponding to identifier.
    """
    url = _AWS_METADATA_URI.format(identifier)
    session = requests.Session()
    session.trust_env = False  # Ignore http_proxy setting for this
    return session.get(url, timeout=2).content

  def get_instance_ids(self, hosts):
    """Given a list of EC2 hosts, get a list of EC2 instance ids.

    Args:
      hosts - list(str) - List of EC2 host strings.

    Returns:
      A list of EC2 instance ids.
    """
    return [self.get_instance_id(host) for host in hosts]

  def get_instance_id(self, hostname):
    """Given an EC2 host, get its EC2 instance id.

    Args:
      hostname - str - EC2 host string.

    Returns:
      An EC2 instance id.
    """
    filters = {'dns-name': hostname}
    reservation = self.conn.ec2.get_all_instances(filters=filters)
    return reservation[0].instances[0].id

class BotoConnectionManager(object):
  """Connection manager for Boto.
  """
  def __init__(self, region, access_key=None, secret_key=None):
    """
    Args:
      region - str - AWS region (EG: 'us-east-1').
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
    """
    self._region = region
    self._access_key = access_key
    self._secret_key = secret_key

  def _make_conn(self, module):
    """
    Given a boto top level module, return a boto connection.

    Args:
      module - module - boto module with connect_to_region available.

    Returns:
      A boto connection instance.
    """
    return module.connect_to_region(self._region,
                                    aws_access_key_id=self._access_key,
                                    aws_secret_access_key=self._secret_key)

  @property
  def ec2(self):
    """
    A boto EC2 connection.
    """
    if not getattr(self, '_ec2', None):
      self._ec2 = self._make_conn(boto.ec2)
    return self._ec2

  @property
  def elb(self):
    """
    A boto ELB connection.
    """
    if not getattr(self, '_elb', None):
      self._elb = self._make_conn(boto.ec2.elb)
    return self._elb

  @property
  def route53(self):
    """
    A boto Route53 connection.
    """
    if not getattr(self, '_route53', None):
      self._route53 = self._make_conn(boto.route53)
    return self._route53
