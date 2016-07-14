from tellapart.aurproxy.backends.backend import ProxyBackend

class NullProxyBackend(ProxyBackend):
  NAME = "null"

  def __init__(self, configuration, signal_update_fn):
    pass

  def signal_update(self):
    pass

  @property
  def blueprints(self):
    return []

  def start_discovery(self, weight_adjustment_start):
    pass

  def update(self, restart_proxy):
    pass

  def restart(self):
    pass

  @property
  def metrics_publisher(self):
    pass
