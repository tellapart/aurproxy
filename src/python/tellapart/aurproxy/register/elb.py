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

"""Registration implementation for AWS Elastic Load Balancers.
"""

__copyright__ = 'Copyright (C) 2015 TellApart, Inc. All Rights Reserved.'

from tellapart.aurproxy.register.aws import AwsRegisterer
from tellapart.aurproxy.register.base import (
  RegistrationAction,
  RegistrationActionReason
)
from tellapart.aurproxy.util import get_logger

logger = get_logger(__name__)


class BaseElbRegisterer(AwsRegisterer):
  def __init__(self, elb_names, region, query_by_ip=False, access_key=None, secret_key=None):
    """
    Common code for ELB Registerers.

    Args:
      elb_names - str - Comma-delimited list of ELB names.
      region - str - AWS region (EG: 'us-east-1').
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
    """
    super(BaseElbRegisterer, self).__init__(region, query_by_ip, access_key, secret_key)
    self._elb_names = elb_names.split(',')

  @property
  def elbs(self):
    """
    Retrieving boto.ec2.elb.loadbalancer.LoadBalancer instances.

    Returns:
      List of boto.ec2.elb.loadbalancer.LoadBalancers.
    """
    elb_conn = self.conn.elb
    return elb_conn.get_all_load_balancers(load_balancer_names=self._elb_names)

  def _get_elb_instance_ids(self, elb):
    """
    Get instance_ids registered on an ELB.

    Args:
      elb - boto.ec2.elb.loadbalancer.LoadBalancer

    Returns:
      List(str) of instance_ids registered to elb.
    """
    return [i.id for i in elb.instances]

class ElbSelfRegisterer(BaseElbRegisterer):
  """
  Registerer that adds and removes current machine from configured ELBs.
  """

  def add(self):
    """
    Add the current instance to all configured ELBs.
    Assumes that this code is running on an EC2 instance.
    """
    instance_id = self.get_current_instance_id()
    for elb in self.elbs:
      # TODO(Thanos): Confirm that ELB has a listener routing to the port that
      # TODO(Thanos): this aurproxy task is running on. Otherwise a
      # TODO(Thanos): misconfiguration could result in traffic going to an
      # TODO(Thanos): aurproxy task from another job.
      if instance_id not in self._get_elb_instance_ids(elb):
        self.record(elb.name,
                    instance_id,
                    RegistrationAction.REGISTER,
                    [RegistrationActionReason.NOT_YET_REGISTERED])
        elb.register_instances([instance_id])
      else:
        self.record(elb.name,
                    instance_id,
                    RegistrationAction.NONE,
                    [RegistrationActionReason.ALREADY_REGISTERED])

  def remove(self):
    """
    Remove the current instance from all configured ELBs.
    Assumes that this code is running on an EC2 instance.
    """
    instance_id = self.get_current_instance_id()
    for elb in self.elbs:
      if instance_id in self._get_elb_instance_ids(elb):
        self.record(elb.name, instance_id, RegistrationAction.REMOVE)
        elb.deregister_instances([instance_id])
      else:
        self.record(elb.name,
                    instance_id,
                    RegistrationAction.NONE,
                    [RegistrationActionReason.NOT_ALREADY_REGISTERED])

class ElbJobRegisterer(BaseElbRegisterer):
  def __init__(self, source, elb_names, region, remove_other_instances,
               query_by_ip=False,
               access_key=None, secret_key=None,
               access_key_path=None, secret_key_path=None):
    """
    Registerer that adds and removes all Aurora-announced tasks to and from
    configured ELBs.

    Args:
      source - aurproxy.source.ProxySource - Source whose endpoints describe
        tasks to register.
      elb_names - str - Comma-delimited list of ELB names
      region - str - AWS region (EG: 'us-east-1').
      remove_other_instances - str/bool - Whether to remove instances that are
                                          registered in ELB but not in Aurora.
      access_key - str - Optional AWS access key.
      secret_key - str - Optional AWS secret key.
      access_key_path - str - Optional file system path to AWS access key.
                              Doesn't override explicitly passed access_key.
      secret_key_path - str - Optional file system path to AWS secret key.
                              Doesn't override explicitly passed secret_key.
    """
    if access_key_path and not access_key:
      access_key = self._load_credential(access_key_path)

    if secret_key_path and not secret_key:
      secret_key = self._load_credential(secret_key_path)

    remove_other_instances = self.is_truish(remove_other_instances)

    self._remove_other_instances = remove_other_instances

    self._source = source

    super(ElbJobRegisterer, self).__init__(elb_names, region, query_by_ip,
                                           access_key, secret_key)

  def synchronize(self, write):
    """
    Synchronize tasks in Aurproxy job to configured ELBs.

    Args:
      write - bool - Whether to apply changes.
    """
    hosts = self.get_job_hosts(self._source)
    instance_ids = self.get_instance_ids(hosts)
    for elb in self.elbs:
      self._synchronize_elb(instance_ids, elb,
                            self._remove_other_instances, write)

  def _load_credential(self, credential_path):
    with open(credential_path) as credential_file:
      credential = credential_file.read().rstrip()
    return credential

  def _record_write(self, elb_name, instance_id, action, reasons, write,
                    log_fn=logger.info):
    """
    Helper that records actions taken in a consistent way.

    Args:
      elb_name - str - ELB name.
      instance_id - str - AWS instance id.
      action - str - Action taken (see RegistrationAction).
      reasons - list(str) - List of reasons for action (see
                            RegistrationActionReason).
      write - bool - Whether are being written.
      log_fn - Logger method to use.

    """
    msg = 'write={0}'.format(str(write).upper())
    self.record(elb_name, instance_id, action, reasons, msg, log_fn)

  def _synchronize_elb(self, instance_ids, elb,
                       remove_other_instances, write):
    """
    Synchronize an ELB configuration to include (possibly only) a specific set
    of instances.

    Args:
      instance_ids - list(str) - List of EC2 instance ids.
      elb - boto.ec2.elb.loadbalancer.LoadBalancer - ELB to synchronize.
      remove_other_instances - whether to remove instances not in instance_ids.
      write - whether to apply changes.
    """
    elb_instance_ids = self._get_elb_instance_ids(elb)
    not_yet_registered = set(instance_ids) - set(elb_instance_ids)
    already_registered = set(elb_instance_ids) & set(instance_ids)
    other_instances = set(elb_instance_ids) - set(instance_ids)

    # TODO(Thanos): Confirm that ELB has a listener routing to the port that
    # TODO(Thanos): this aurproxy task is running on. Otherwise a
    # TODO(Thanos): misconfiguration could result in traffic going to an
    # TODO(Thanos): aurproxy task from another job.

    for instance_id in not_yet_registered:
      self._record_write(elb.name,
                         instance_id,
                         RegistrationAction.REGISTER,
                         [RegistrationActionReason.NOT_YET_REGISTERED],
                         write)
      if write:
        elb.register_instances([instance_id])

    for instance_id in already_registered:
      self._record_write(elb.name,
                         instance_id,
                         RegistrationAction.NONE,
                         [RegistrationActionReason.ALREADY_REGISTERED],
                         write)

    for instance_id in other_instances:
      if remove_other_instances:
        reasons = [RegistrationActionReason.ALREADY_REGISTERED,
                   RegistrationActionReason.NO_CORRESPONDING_TASK]
        self._record_write(elb.name,
                           instance_id,
                           RegistrationAction.REMOVE,
                           reasons,
                           write)
        if write:
          elb.deregister_instances([instance_id])
      else:
        action = RegistrationAction.NONE
        reasons = [RegistrationActionReason.REMOVE_OTHER_INSTANCE_FALSE]
        self._record_write(elb.name, instance_id, action, reasons, write)
