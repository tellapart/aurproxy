# aurproxy

aurproxy is a load balancer manager with knowledge of
[Apache Aurora's](http://aurora.incubator.apache.org/) service discovery
mechanism and integration with Aurora's task lifecycle. It is a python
application that manages a fully featured but not Aurora-aware load balancer
(currently only nginx is supported). When Aurora service discovery events
occur, aurproxy detects them, rewrites the load balancer's configuration
file and then triggers a graceful restart of the load balancer. Use aurproxy
to expose dynamic Aurora service endpoints to services and applications that
don't have knowledge of Aurora's service discovery mechanism.


## Features

- Battle tested at TellApart
  - EC2 Classic-hosted Aurora cluster
  - Regularly proxies ~150k QPS in production
- Load balance HTTP (nginx)
- Load balance TCP (nginx)
- Active healthchecks for managed endpoints
- Delayed start for new endpoints
- Traffic ramping for new endpoints
- Simple overload protection
- HTTP traffic mirroring & replay modes
  - Using [gor](https://github.com/buger/gor)
- Route HTTP requests to a pool of endpoints from multiple jobs
- Route HTTP requests based on HTTP route
- Route HTTP requests based on HTTP "Host" header
- Register and deregister aurproxy task instance with upstream services
  - DNS (Route53)
  - Other load balancers (ELBs)

## Try it

### Locally

Replace your zk_servers, role, environment, job, etc. in the value of the
"config" argument below:

    # 1 - Build and push container to your registry - replace registry address.
    PACKAGE_VERSION=20150430.0; docker build -t docker.mydomain.com/library/aurproxy:$PACKAGE_VERSION . && docker push docker.mydomain.com/library/aurproxy:$PACKAGE_VERSION

    # 2 - Launch container
    docker run -t -i --net=host docker.mydomain.com/aurproxy:20150430.0 bash

    # 3 - Run setup to configure load balancer
    cd /opt/aurproxy && \
    python -m "tellapart.aurproxy.command" run \
      --setup \
      --management-port=31325 \
      --config '{"backend": "nginx", "servers": [{"routes": [{"sources": [{"endpoint": "http", "zk_servers": "0.zk.mycluster.mydomain.com:2181,1.zk.mycluster.mydomain.com:2181,2.zk.mycluster.mydomain.com:2181", "environment": "devel", "job": "web", "role": "myrole", "source_class": "tellapart.aurproxy.source.AuroraProxySource"}], "locations": ["/"]}], "hosts": ["default"], "ports": [8080], "context": {"default_server": "True", "location_blacklist": ["/health", "/quitquitquit", "/abortabortabort"]}}]}'

    # 4 - Start load balancer
    /usr/sbin/nginx -c /etc/nginx/nginx.conf &

    # 5 - Re-run #2 without --setup flag.

    # 6 - Test from another shell - assuming host networking
    # (otherwise you'll have to map port through in #1 above)
    # and something to point to in configured ProxySource.
    curl 127.0.0.1:8080/robots.txt


### On Aurora devcluster

1. Set up [Aurora devcluster](https://github.com/apache/incubator-aurora/blob/master/docs/vagrant.md)

2. Build and push container to your registry - replace registry address.

        PACKAGE_VERSION=20150430.0; docker build -t docker.mydomain.com/library/aurproxy:$PACKAGE_VERSION . && docker push docker.mydomain.com/library/aurproxy:$PACKAGE_VERSION

3.  Edit example/aurproxy_hello_world.aur to match the information for the docker image above.

4. Copy example/aurproxy_hello_world.aur, example/hello_world.aur,
   example/hello_world.py to your local aurora source directory
   (will show up in "/vagrant/" in devcluster).

5. "vagrant ssh" into aurora devcluster instance.

6. Install hello_world.py prerequisites:

        apt-get install python-pip
        pip install Flask==0.10.1

7. Create jobs:

        aurora job create devcluster/www-data/devel/hello_world /vagrant/hello_world.aur
        aurora job create devcluster/www-data/devel/aurproxy /vagrant/aurproxy_hello_world.aur

8. Wait for the jobs to come up - the first download of the aurproxy docker image may take a while:

        http://192.168.33.7:8081/scheduler/www-data/devel/aurproxy

9. Test from host:

        curl 192.168.33.7:8080
        # Expect 200 "Hello World!"

10. Find running aurproxy task instance in Aurora web interface, open stderr of
   "aurproxy" process.

11. Restart hello_world job while watching aurproxy stderr log to see proxy
   configuration update in action:

        aurora job restart devcluster/www-data/devel/hello_world


## Deployment Suggestions:
- Make sure that Mesos' Docker containerizer is configured for Host mode networking.
 - Currently the [default](https://git-wip-us.apache.org/repos/asf?p=mesos.git;a=blob;f=docs/docker-containerizer.md#l51)
- If you need aurproxy to listen on a fixed port (say, 80), make sure that it
  isn't in your ephemeral port range and then set your job up to be run in a
  dedicated group with a "host" constraint value of "limit:1" in order to
  ensure only 1 aurproxy task instance per slave for that job.

## Traffic Mirroring & Replay Modes:

Aurproxy HTTP traffic mirroring and replay features use
[gor](https://github.com/buger/gor), which can be set up to mirror a fixed
number of queries per second from a full aurproxy task instance over a TCP
stream to one or more gor replay servers. Aurproxy finds gor instances using
sources, and will update its gor command line to add new endpoints as they
appear and remove old ones as they disappear.

To use traffic mirroring:

1. Set up a gor replay server. It can be but doesn't have to be in Aurora.
   See "traffic replay" for instructions on how to set one up using aurproxy
   to manage it.
2. Add a gor_process to your Aurproxy task definition.

        # max_failures=0 is important:
        # aurproxy kills the gor process when it updates mirror.sh,
        # and max_failures=0 means that Aurora won't treat the task as
        # unhealthy after some number of gor process restarts.
        gor_process = Process(
          name='gor',
          cmdline='/etc/aurproxy/gor/dynamic.sh',
          max_failures=0)

3. Pass values for mirror_source (an aurproxy source configured to point to
   your gor replication server(s)), mirror_ports, mirror_max_qps, and
   mirror_max_update_frequency into aurproxy when starting it.

To use traffic replay:

1. Set up a replay job to run aurproxy "run_replay" with the "--setup" flag and
   then both run_replay and gor, as per above in the traffic mirroring
   instructions. run_replay command line example:

        cd /opt/aurproxy && \
        python -m tellapart.aurproxy.command run_replay \
          --management-port 12345 \
          --replay-port 12346 \
          --replay-source '{"name": "replay", "source_class": "tellapart.aurproxy.source.ApiSource"}' \
          --replay-max-qps 1000


## Lifecycle
1. Setup
    1. Configure proxy (nginx.conf)
2. Start proxy (nginx)
3. Run aurproxy
    1. Initialize metrics collection plugin, if configured.
    2. Initialize and execute registration plugin, if configured.
    3. Initialize and start proxy updater.
        1. Periodically check for update requests signaled by proxy sources and
           share adjusters.
        2. If need to update is signaled, update proxy configuration and
           restart proxy.
    4. Start aurproxy's web server
        1. Listens for Aurora lifecycle events - health, shutdown, etc.
4. Aurora signals aurproxy task instance should shut down (/quitquitquit)
    1. Run shutdown handlers.
        1. Deregister, if registration plugin configured.
        1. Flush metrics.


## Develop

### Build

Build the image. EG:

    docker build -t docker.mydomain.com/aurproxy:latest .

### Test

#### Set up for testing

    pip install virtualenv
    virtualenv -p python2.7 --no-site-packages --distribute ~/.virtualenvs/aurproxy
    cd ~/src/aurproxy
    source ~/.virtualenvs/aurproxy/bin/activate
    pip install -r ~/src/aurproxy/requirements.txt
    pip install -r ~/src/aurproxy/requirements_dev.txt

#### Run tests

    nosetests --all-modules --where ./tellapart --with-coverage --cover-package=tellapart.aurproxy --cover-inclusive


## Terminology

### Backends
aurproxy is designed to support using different load balancers as backends.
Within aurproxy, a backend extends aurproxy.backends.ProxyBackend and is where
the loadbalancer-specific logic and management code should live. nginx is
currently the only backend implementation, but an HAProxy backend
implementation should be possible.

### Endpoints
Endpoints are host+port pairs that represent a running task instance.
They don't have to be hosted in Aurora.

### Sources
Sources are classes that are responsible for providing, maintaining, and
signaling updates to a list of endpoints.

### Source Lifecycle
1. Setup
2. Start
    1. Set up watches on service discovery data sources, if necessary.
3. Ongoing:
    1. On update (node being added or removed), signal that an update is
       required.
    2. Return list of SourceEndpoints whenever requested.

### Source Implementations
1. **AuroraSource**, which watches Aurora's service discovery database in
   Zookeeper and whenever a ServiceInstance is added or removed, signals
   Aurproxy's ProxyUpdater that an update is required.
2. **StaticProxySource**, which returns a single, statically configured endpoint.

### Registration

#### Active Registration
Active Registration refers to registration events that take place during the
normal Aurora lifecycle for Aurproxy task instances - on startup, registration
is triggered (if configured), and on graceful shutdown, deregistration is
triggered (if configured).

### Active Registration Implementations
- ELB

        --registration-arg=region=us-east-1
        --registration-arg=elb_names=MyElb
        --registration-class=tellapart.aurproxy.register.elb.ElbSelfRegisterer

- Route53

        --registration-arg=region=us-east-1
        --registration-arg=domain=myproxy.mydomain.com
        --registration-arg=hosted_zone_id={{hosted_zone}}
        --registration-arg=ttl=60
        --registration-class=tellapart.aurproxy.register.route53.Route53SelfRegisterer

#### Synchronization
Synchronization refers to a way to run a registration plugin as an
administrative script or as an Aurora cron job. It is intended to both remove
outdated aurproxy tasks left behind by slaves that may have disappeared or on
which task shutdown was not graceful as well as add missing any aurproxy tasks
o supported systems (EG: other load balancers or DNS).

### Synchronization Implementations
- ELB

        cd /opt/aurproxy && python -m "aurproxy.command" synchronize \
        --registration-arg=region=us-east-1 \
        --registration-arg=elb_names=MyElb \
        --registration-class=tellapart.aurproxy.register.elb.ElbJobRegisterer

- Route53

        cd /opt/aurproxy && python -m "aurproxy.command" synchronize \
        --registration-arg=region=us-east-1 \
        --registration-arg=domain=myproxy.mydomain.com \
        --registration-arg=hosted_zone_id={{hosted_zone}} \
        --registration-arg=ttl=60 \
        --registration-class=tellapart.aurproxy.register.route53.Route53JobRegisterer


### Metrics
Aurproxy supports recording:

- aurproxy metrics (restart attempts, etc.)
- Proxy backend metrics (nginx stats)

### Metrics Implementations
- Librato

        --metric-publisher-class=tellapart.aurproxy.metrics.publisher.LibratoMetricPublisher \
        --metric-publisher-arg=source={{cluster}}.{{role}}.{{environment}}.{{job}} \
        --metric-publisher-arg=period=60 \
        --metric-publisher-arg=api_user={{librato_user}} \
        --metric-publisher-arg=api_token={{librato_token}}

- OpenTSDB

        --metric-publisher-class=tellapart.aurproxy.metrics.publisher.OpenTSDBMetricPublisher \
        --metric-publisher-arg=source={{cluster}}.{{role}}.{{environment}}.{{job}} \
        --metric-publisher-arg=period=60 \
        --metric-publisher-arg=prefix=apps. \
        --metric-publisher-arg=host=localhost \
        --metric-publisher-arg=port=4242


### Log Aggregation
Currently, the only log aggregation implementation is Sentry. If you pass a
sentry_dsn in via the command line, logged exceptions will be recorded to
Sentry.

    --sentry-dsn='gevent+https://{{sentry_user}}:{{sentry_pass}}@app.getsentry.com/{{sentry_project}}'


## Configuration Elements
### Aurproxy Configuration (JSON String)
- **servers:** Required list of one or more ProxyServer dictionaries
- **backend:** Required name of backend to use. Use 'nginx'.
- **context:** Optional dictionary. See "context" note below.

### ProxyServer
- **routes:** Optional list of one or more ProxyRoute dictionaries. Use routes
  for HTTP load balancing. At least one route or one stream must be set.
- **streams:** Optional list of one or more ProxyStream dictionaries. Use
  streams for TCP load balancing. At least one route or one stream must be set.
- **ports:** Required list of one or more ports to listen on. Shouldn't collide
  with other ports in use. Use dedicated group + host limit constraints to
  control.
- **healthcheck_route:** Optional HTTP route (EG: "/health"). Will always
  return 200 if set. Only applied to ProxyRoutes.
- **context:** Optional dictionary. See "context" note below.

### ProxyRoute
- **locations:** Required list with one or more HTTP routes (EG: ["/"])
- **sources:** Required list with one or more ProxySource dictionaries
- **empty_endpoint_status_code:** Optional status code to return if there are
  no available endpoints. Defaults to 503 (Service Unavailable) if not
  specified.
- **overflow_sources:** Optional list of one or more ProxySource dictionaries
- **overflow\_threshold\_pct:** Optional threshold past which traffic will be
  sent to overflow_source.

### ProxyStream
- **sources:** Required list with one or more ProxySource dictionaries
- **overflow_sources:** Optional list of one or more ProxySource dictionaries
- **overflow\_threshold\_pct:** Optional threshold past which traffic will be
  sent to overflow_source.

### ProxySource (Base)
- **source_class:** Python class path for source type.
  EG: tellapart.aurproxy.source.AuroraSource
- **share_adjusters:** Optional list of ShareAdjuster dictionaries.

### AuroraSource
- **source_class:** 'tellapart.aurproxy.source.AuroraSource'
- **role:** Required Aurora job role string
- **environment:** Required Aurora job environment string
- **job:** Required Aurora job name string
- **zk_servers:** Required comma-separated list in string of ZooKeeper servers
  with Aurora Service Discovery registry
- **announcer_serverset_path:** Optional ZooKeeper path under which Aurora
  Service Discovery lives. Default: '/aurora/'
- **share_adjusters:** Optional list of ShareAdjuster dictionaries.

### StaticProxySource
- **source_class:** 'tellapart.aurproxy.source.StaticProxySource'
- **name:** Required name of static source (EG: 'devnull')
- **host:** Required host for static endpoint (EG: '127.0.0.1')
- **port:** Required port for static endpoint (EG: 12345)
- **share_adjusters:** Optional list of ShareAdjuster dictionaries.

### ApiSource
- **source_class:** 'tellapart.aurproxy.source.ApiSource'
- **name:** Required name of static source (EG: 'replay')
- **source_whitelist:** Optional list(str) of source class paths that are
  allowed to be created under ApiSource.

### ShareAdjuster (Base)
- **share_adjuster_class:** Required python class path for share adjuster type.

### RampingShareAdjuster
- **share_adjuster_class:** 'tellapart.aurproxy.share.adjusters.RampingShareAdjuster'
- **ramp_delay:** Required, number of seconds before starting to ramp traffic
  up. (EG: 90)
- **ramp_seconds:** Required, number of seconds over which to ramp traffic up.
  (EG: 60)
- **update_frequency:** Required, how often need to update is signaled to proxy
  updater.
- **curve:** Optional, type of curve along which to ramp traffic. Currently
  only supports "linear".

### HttpHealthCheckShareAdjuster
- **share_adjuster_class:** 'tellapart.aurproxy.share.adjusters.HttpHealthCheckShareAdjuster'
- **route:** Route to healthcheck. (EG: '/health')
- **interval:** Number of seconds between checks. (EG: 3)
- **timeout:** Number of seconds after which to time out a check. (EG: 2)
- **unhealthy_threshold:** Number of failed checks before a healthy task is
  marked as being unhealthy. (EG: 2)
- **healthy_threshold:** Number of failed checks before an unhealthy task is
  marked as being healthy. (EG: 2)
- **http_method:** Which http method to use for healthchecks (EG: HEAD or GET)

### Context
Some of the configuration elements above support a "context" dictionary. This
a "bucket of stuff" that gets passed directly down to the configuration
rendering context and is the place to put backend-specific configuration
values (EG: "default_server": True)

#### NginxServerContext
- **default_server:** boolean, whether to treat this server as the default (vs
  requiring a Host header match).
- **location_blacklist:** list(str), nginx-style locations for which to deny
  requests for this server.

### Configuration Example

    import json

    cmd = 'cd /opt/aurproxy && python -m "tellapart.aurproxy.command" run ' \
          '--setup --management-port=31325 --max-update-frequency=10 ' \
          '--update-period=2 --sentry-dsn='' --config \''
    config = {
        "servers": [
            {
                "routes": [
                    {
                        "sources": [
                            {
                                "endpoint": "http",
                                "announcer_serverset_path": "sd/mycluster",
                                "job": "myjob",
                                "environment": "prod",
                                "zk_servers": "0.zk.mycluster.mydomain.com:2181,"
                                              "1.zk.mycluster.mydomain.com:2181,"
                                              "2.zk.mycluster.mydomain.com:2181",
                                "role": "myrole",
                                "source_class": "tellapart.aurproxy.source.AuroraProxySource",
                                "share_adjusters": [
                                    {
                                        "share_adjuster_class": "tellapart.aurproxy.share.adjusters.RampingShareAdjuster",
                                        "ramp_seconds": 60,
                                        "ramp_delay": 10,
                                        "update_frequency": 10,
                                        "curve": "linear"
                                    },
                                    {
                                        "share_adjuster_class": "tellapart.aurproxy.share.adjusters.HttpHealthCheckShareAdjuster",
                                        "route": "/health",
                                        "interval": 3,
                                        "timeout": 2,
                                        "unhealthy_threshold": 2,
                                        "healthy_threshold": 2,
                                    }
                                ]
                            }
                        ],
                        "locations": [
                            "/"
                        ]
                    }
                ],
                "healthcheck_route": "/healthcheck",
                "hosts": [
                    "default"
                ],
                "ports": [
                    10080
                ],
                "context": {
                    "default_server": "True",
                    "location_blacklist": ["/health", "/quitquitquit", "/abortabortabort"]
                }
            }
        ],
        "backend": "nginx"
    }
    cmd += json.dumps(config) + '\''
    print cmd
