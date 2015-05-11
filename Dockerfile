# Newer python base images may break gevent.
# See https://github.com/docker-library/python/issues/29#issuecomment-70727289
FROM python:2.7.7
MAINTAINER thanos@tellapart.com


######
# System prerequisite installation
######

# Update apt repository
RUN apt-get update

# Install python prerequisites
RUN apt-get install -y python-pip python-dev build-essential

# Install go
RUN apt-get install -y golang

# Install gor
ENV GOPATH=/opt/go
RUN mkdir -p $GOPATH \
 && go get github.com/buger/gor \
 && cd $GOPATH/src/github.com/buger/gor \
 && go build

# Install nginx
ENV NGX_REQS openssl libssl1.0.0 libxml2 libxslt1.1 libgeoip1 libpcre3 zlib1g
RUN apt-get update \
 && apt-get install -y $NGX_REQS \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV NGX_DEV_KIT_VER 0.2.19
ENV NGX_VER 1.7.10
ENV NGX_MD5 8e800ea5247630b0fcf31ba35cb3245d
ENV NGX_STATSD_VER b756a12abf110b9e36399ab7ede346d4bb86d691
ENV NGX_HEADERS_MORE_VER 0.26
ENV NGX_ECHO_VER 0.57
ENV DEV_PKGS build-essential curl libpcre3-dev zlib1g-dev libssl-dev libxml2-dev libgeoip-dev

RUN apt-get update \
 && apt-get install -y $DEV_PKGS \
 && mkdir -p /tmp/build && cd /tmp/build \
 && curl -s -L -o ngx_devel.tar.gz \
      https://github.com/simpl/ngx_devel_kit/archive/v$NGX_DEV_KIT_VER.tar.gz \
 && curl -s -L -o ngx.tar.gz \
      http://nginx.org/download/nginx-$NGX_VER.tar.gz \
 && curl -s -L -o ngx_statsd.tar.gz \
      https://github.com/zebrafishlabs/nginx-statsd/archive/$NGX_STATSD_VER.tar.gz \
 && curl -s -L -o ngx_headers_more.tar.gz \
      https://github.com/openresty/headers-more-nginx-module/archive/v$NGX_HEADERS_MORE_VER.tar.gz \
 && curl -s -L -o ngx_echo.tar.gz \
      https://github.com/openresty/echo-nginx-module/archive/v$NGX_ECHO_VER.tar.gz \
 && echo "$NGX_MD5 ngx.tar.gz" | md5sum -c - || (echo "MD5 for ngx.tar.gz didn't match expected!" && exit 1) \
 && tar -xvf ngx_devel.tar.gz \
 && tar -xvf ngx.tar.gz \
 && tar -xvf ngx_statsd.tar.gz \
 && tar -xvf ngx_headers_more.tar.gz \
 && tar -xvf ngx_echo.tar.gz \
 && cd /tmp/build/nginx-$NGX_VER \
 && ./configure --prefix=/usr \
                --conf-path=/etc/nginx/nginx.conf \
                --error-log-path=/var/log/nginx/error.log \
                --http-client-body-temp-path=/var/lib/nginx/body \
                --http-fastcgi-temp-path=/var/lib/nginx/fastcgi \
                --http-log-path=/var/log/nginx/access.log \
                --http-proxy-temp-path=/var/lib/nginx/proxy \
                --http-scgi-temp-path=/var/lib/nginx/scgi \
                --http-uwsgi-temp-path=/var/lib/nginx/uwsgi \
                --lock-path=/var/lock/nginx.lock \
                --pid-path=/var/run/nginx.pid \
                --with-debug \
                --with-http_addition_module \
                --with-http_dav_module \
                --with-http_geoip_module \
                --with-http_gzip_static_module \
                --with-http_realip_module \
                --with-http_stub_status_module \
                --with-http_ssl_module \
                --with-http_sub_module \
                --with-ipv6 \
                --with-sha1=/usr/include/openssl \
                --with-md5=/usr/include/openssl \
                --add-module=/tmp/build/nginx-statsd-$NGX_STATSD_VER/ \
                --add-module=/tmp/build/headers-more-nginx-module-$NGX_HEADERS_MORE_VER \
                --add-module=/tmp/build/echo-nginx-module-$NGX_ECHO_VER \
 && make -j4 \
 && make install \
 && cd / \
 && rm -rf /tmp/build \
 && apt-get purge -y $DEV_PKGS \
 && apt-get autoremove -y \
 && apt-get purge -y \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/nginx/sites-enabled \
 && mkdir -p /etc/nginx/sites-available \
 && mkdir -p /var/lib/nginx

######
# System prerequisite configuration
######

# Set up run directory for pids
RUN mkdir -p /var/run

# Remove default nginx config
RUN rm /etc/nginx/nginx.conf

# Symlink aurproxy nginx config
RUN mkdir -p /etc/aurproxy/nginx
RUN ln -sf /etc/aurproxy/nginx/nginx.conf /etc/nginx

# Create dynamic gor config location
RUN mkdir -p /etc/aurproxy/gor

######
# Application prerequisite installation
######

# Set up application sandbox
# (Gets mounted by aurora in production)
RUN mkdir -p /mnt/mesos/sandbox/sandbox

# Set up application directory
RUN mkdir -p /opt/aurproxy/

# Add application requirements
ADD ./requirements.txt /opt/aurproxy/requirements.txt

#  Install application requirements
RUN pip install -r /opt/aurproxy/requirements.txt


######
# Application setup
######
ADD ./tellapart/__init__.py /opt/aurproxy/tellapart/__init__.py
ADD ./tellapart/aurproxy /opt/aurproxy/tellapart/aurproxy
ADD ./templates /opt/aurproxy/tellapart/aurproxy/templates

# Not intended to be run
# Command will come from aurproxy.aur
CMD ["echo done"]
