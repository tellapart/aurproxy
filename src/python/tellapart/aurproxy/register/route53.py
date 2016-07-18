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

"""Registration implementation for AWS Route53 DNS.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from boto.route53.record import (
  Record,
  ResourceRecordSets
)
from boto.route53.zone import Zone
from collections import namedtuple
import functools

from tellapart.aurproxy.register.aws import AwsRegisterer
from tellapart.aurproxy.register.base import (
  RegistrationAction,
  RegistrationActionReason
)
from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)

class RecordType(object):
  CNAME = 'CNAME'

Route53Record = namedtuple('Route53Record', ('domain', 'hostname', 'ttl'))

class BaseRoute53Registerer(AwsRegisterer):
  """Common code for Route53 Registerers.
  """
  def __init__(self, domain, hosted_zone_id, region, ttl, query_by_ip=False, access_key=None,
               secret_key=None):
    """
    Args:
      domain - str - The domain to be registered.
      hosted_zone_id - str - The Hosted Zone ID for the domain.
      region - str - AWS region (EG: 'us-east-1').
      ttl - int - The TTL for the registration.
      query_by_ip - bool - If true, resolves the hostname and uses the IP find instances
                           rather than the hostname.
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
    """
    super(BaseRoute53Registerer, self).__init__(region, query_by_ip, access_key, secret_key)
    self._domain = domain
    self._hosted_zone_id = hosted_zone_id
    self._ttl = int(ttl)

  def _get_records(self):
    """
    Returns all Route53 records for the domain.
    """
    zone = Zone(self.conn.route53, {'Id': self._hosted_zone_id})
    result = zone.find_records(self._domain, RecordType.CNAME, all=True)
    # Always return a list of records.
    if not result:
      return []
    elif isinstance(result, Record):
      return [result]
    else:
      return result

  def _get_record_identifiers(self):
    """
    Returns all Route53 identifiers for the domain.
    """
    return [record.identifier for record in self._get_records()]

  def _register(self, hostname):
    """Registers a hostname with the domain. If the hostname is already
    registered, this is a noop.

    Args:
      hostname - The public DNS of the AWS instance.

    Returns:
      True if the hostname was registered, False otherwise.
    """
    existing_records = self._get_records()
    if hostname not in [r.identifier for r in existing_records]:
      # All members of a record set must have the same TTL. If no records exist
      # for the domain, we'll use the TTL as specified. Otherwise, use the TTL
      # of the first member of the set.
      ttl = int(existing_records[0].ttl) if existing_records else self._ttl
      if ttl != self._ttl:
        logger.warn(
            'Mismatched TTL encountered when registering host %s to domain %s. '
            'Using existing TTL of %s instead of configured value of %s.',
            hostname, self._domain, ttl, self._ttl)
      record = Route53Record(
          domain=self._domain, hostname=hostname, ttl=ttl)
      self._update_recordset('CREATE', record)
      return True

    return False

  def _unregister(self, hostname):
    """Unregisters a hostname with the domain. If the hostname is not already
    registered, this is a noop.

    Args:
      hostname - The public DNS of the AWS instance.

    Returns:
      True if the hostname was unregistered, False otherwise.
    """
    records = [r for r in self._get_records() if r.identifier == hostname]
    # If there is no record registered for the hostname, do nothing.
    if not records:
      return False
    elif len(records) > 1:
      msg = 'Multiple records for hostname. Existing records are: %s' % records
      self.record(
          self._domain,
          hostname,
          RegistrationAction.NONE,
          RegistrationActionReason.NO_REASON,
          msg,
          logger.error)
      return False
    else:
      # We consider domain/record type/identifier to be the primary key, but AWS
      # will reject a delete if the TTL does not match. Pull the existing record
      # and use its TTL instead of the TTL for new records.
      existing_ttl = int(records[0].ttl)
      if existing_ttl != self._ttl:
        logger.warn(
            'Mismatched TTL encountered when unregistering host %s from domain '
            '%s. Using existing TTL of %s instead of configured value of %s.',
            hostname, self._domain, existing_ttl, self._ttl)
      record = Route53Record(
          domain=self._domain, hostname=hostname, ttl=existing_ttl)
      self._update_recordset('DELETE', record)
      return True

  def _update_recordset(self, action, records):
    """Take a specific action on a recordset with a collection of records.

    Args:
      action - The action to take (CREATE, DELETE)
      records - An iterable of Route53Record objects or a single Route53Record.
    """
    if isinstance(records, Route53Record):
      records = [records]

    record_set = ResourceRecordSets(self.conn.route53, self._hosted_zone_id)
    for r in records:
      change = record_set.add_change(
          action=action,
          name=r.domain,
          type=RecordType.CNAME,
          identifier=r.hostname,
          ttl=r.ttl,
          weight=1)
      change.add_value(r.hostname)
    record_set.commit()

class Route53SelfRegisterer(BaseRoute53Registerer):
  """
  Registerer that adds and removes current machine from the configured domain.
  """

  def add(self):
    """
    Add the current instance to the configured domain.
    Assumes that this code is running on an EC2 instance.
    """
    public_hostname = self.get_public_hostname()
    registered = self._register(public_hostname)

    if registered:
      self.record(
        self._domain,
        public_hostname,
        RegistrationAction.REGISTER,
        RegistrationActionReason.NOT_YET_REGISTERED)
    else:
      self.record(
        self._domain,
        public_hostname,
        RegistrationAction.NONE,
        RegistrationActionReason.ALREADY_REGISTERED)

  def remove(self):
    """
    Remove the current instance from the configured domain.
    Assumes that this code is running on an EC2 instance.
    """
    public_hostname = self.get_public_hostname()
    unregistered = self._unregister(public_hostname)
    if unregistered:
      self.record(self._domain, public_hostname, RegistrationAction.REMOVE)
    else:
      self.record(
        self._domain,
        public_hostname,
        RegistrationAction.NONE,
        RegistrationActionReason.NOT_ALREADY_REGISTERED)

class Route53JobRegisterer(BaseRoute53Registerer):
  """Registerer that adds and removes all Aurora-announced tasks to and from
  the configured domain.
  """
  def __init__(self, source, domain, hosted_zone_id, region, ttl,
               remove_other_instances, access_key=None, secret_key=None):
    """
    Args:
      source - aurproxy.source.ProxySource - Source whose endpoints describe
        tasks to register.
      domain - str - The domain to be registered.
      hosted_zone_id - str - The Hosted Zone ID for the domain.
      region - str - AWS region (EG: 'us-east-1').
      ttl - int - The TTL for the registration.
      remove_other_instances - str/bool - Whether to remove instances that are
                                          registered in ELB but not in Aurora.
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
    """
    remove_other_instances = self.is_truish(remove_other_instances)
    self._remove_other_instances = remove_other_instances
    self._source = source

    super(Route53JobRegisterer, self).__init__(
        domain, hosted_zone_id, region, ttl, access_key, secret_key)

  def synchronize(self, write):
    """
    Synchronize tasks in Aurproxy job to the configured domain.

    Args:
      write - bool - Whether to apply changes.
    """
    # All hosts that are currently announced for the instance of aurproxy.
    announced_hosts = self.get_job_hosts(self._source)

    # All hosts that are currently registered with DNS.
    registered_hosts = self._get_record_identifiers()

    # Hosts that are announced but not registered with DNS.
    not_yet_registered = set(announced_hosts) - set(registered_hosts)
    # Hosts that are announced and are already registered.
    already_registered = set(registered_hosts) & set(announced_hosts)
    # Hosts that are registered in DNS but not announced.
    other_instances = set(registered_hosts) - set(announced_hosts)

    msg = 'write={0}'.format(str(write).upper())
    record_write = functools.partial(
        self.record, resource_name=self._domain, msg=msg)

    for hostname in not_yet_registered:
      record_write(
          instance_id=hostname,
          action=RegistrationAction.REGISTER,
          reasons=RegistrationActionReason.NOT_YET_REGISTERED)

      if write:
        self._register(hostname)

    for hostname in already_registered:
      record_write(
          instance_id=hostname,
          action=RegistrationAction.NONE,
          reasons=RegistrationActionReason.ALREADY_REGISTERED)

    for hostname in other_instances:
      if self._remove_other_instances:
        reasons = [RegistrationActionReason.ALREADY_REGISTERED,
                   RegistrationActionReason.NO_CORRESPONDING_TASK]
        record_write(
            instance_id=hostname,
            action=RegistrationAction.REMOVE,
            reasons=reasons)

        if write:
          self._unregister(hostname)
      else:
        record_write(
          instance_id=hostname,
          action=RegistrationAction.NONE,
          reasons=RegistrationActionReason.REMOVE_OTHER_INSTANCE_FALSE)
