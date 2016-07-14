python_library(
    name='lib',
    dependencies=[
      'src/python/tellapart/aurproxy:lib',
      'tests/python/tellapart/aurproxytest/backends',
      'tests/python/tellapart/aurproxytest/backends/nginx',
      'tests/python/tellapart/aurproxytest/share',
      'tests/python/tellapart/aurproxytest/source',
      'tests/python/tellapart/aurproxytest/source/sources',
    ],
    sources=globs('*.py'),
)

python_tests(
      name='test',
      dependencies=[':lib'],
      sources=['mirror.py', 'proxy.py']
)
