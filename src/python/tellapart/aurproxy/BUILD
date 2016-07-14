python_library(
    name = 'lib',
    sources = globs('*.py'),
    dependencies = [
      '3rdparty/python:boto',
      '3rdparty/python:commandr',
      '3rdparty/python:Flask',
      '3rdparty/python:Flask-RESTful',
      '3rdparty/python:gevent',
      '3rdparty/python:Jinja2',
      '3rdparty/python:kazoo',
      '3rdparty/python:librato-metrics',
      '3rdparty/python:psutil',
      '3rdparty/python:python-dateutil',
      '3rdparty/python:raven',
      '3rdparty/python:requests',
      'src/python/tellapart/aurproxy/app',
      'src/python/tellapart/aurproxy/app/module',
      'src/python/tellapart/aurproxy/backends',
      'src/python/tellapart/aurproxy/backends/nginx',
      'src/python/tellapart/aurproxy/config',
      'src/python/tellapart/aurproxy/metrics',
      'src/python/tellapart/aurproxy/register',
      'src/python/tellapart/aurproxy/share',
      'src/python/tellapart/aurproxy/share/adjusters',
      'src/python/tellapart/aurproxy/source',
      'src/python/tellapart/aurproxy/source/sources',
    ],
)

python_binary(
    name='aurproxy',
    entry_point = 'tellapart.aurproxy.command',
    dependencies = [
      ':lib'
    ],
)
