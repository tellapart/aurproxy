# -*- coding: utf-8 -*-

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

from decimal import Decimal
import unittest

from tellapart.aurproxy.register import BaseRegisterer
from tellapart.aurproxy.util import (
  KlassFactory,
  class_from_class_path,
  get_logger,
  load_cli_kwargs,
  load_cli_plugin,
  load_klass_factory,
  load_klass_plugin,
  load_plugin,
  load_registration_plugin,
  run_local,
  slugify)

class ClassFromClassPathTests(unittest.TestCase):
  def test_class_from_class_path(self):
    d_test = class_from_class_path('decimal.Decimal')
    self.assertEqual(d_test, Decimal)

class GetLoggerTests(unittest.TestCase):
  def test_get_logger(self):
    logger = get_logger(__name__)
    self.assertTrue(hasattr(logger, 'debug'))
    self.assertTrue(hasattr(logger, 'info'))
    self.assertTrue(hasattr(logger, 'warning'))
    self.assertTrue(hasattr(logger, 'error'))
    self.assertTrue(hasattr(logger, 'exception'))

class KlassFactoryTstBase(unittest.TestCase):
  def tst_klass_factory(self, callable_factory_creator):
    factory = callable_factory_creator('__builtin__.dict', a=1, b=2)
    instance = factory.build()
    self.assertEqual(instance['a'], 1)
    self.assertEqual(instance['b'], 2)
    instance = factory.build(c=3)
    self.assertEqual(instance['a'], 1)
    self.assertEqual(instance['b'], 2)
    self.assertEqual(instance['c'], 3)

class KlassFactoryTests(KlassFactoryTstBase):
  def test_klass_factory(self):
    self.tst_klass_factory(KlassFactory)

class LoadPluginTests(unittest.TestCase):
  def test_load_plugin(self):
    plugin_instance = load_plugin('decimal.Decimal', value='1')
    self.assertTrue(isinstance(plugin_instance, Decimal))
    self.assertEqual(plugin_instance, 1)

class LoadCliKwargsTests(unittest.TestCase):
  def test_load_cli_kwargs(self):
    pairs = [('a', '1'), ('b', '2')]
    delims = ['=', '==', ';']

    for delim in delims:
      result = load_cli_kwargs([delim.join([k, v]) for k, v in pairs], delim)
      self.assertEquals(result['a'], '1')
      self.assertEquals(result['b'], '2')

    result = load_cli_kwargs([], '=')
    self.assertEquals(result, {})

class LoadCliPluginTests(unittest.TestCase):
  def test_load_cli_plugin(self):
    cli_kwargs = ['a=1', 'b=2']
    instance = load_cli_plugin('__builtin__.dict', cli_kwargs)
    self.assertEquals(instance['a'], '1')
    self.assertEquals(instance['b'], '2')
    extra_kwargs = {'c': '3'}
    instance = load_cli_plugin('__builtin__.dict', cli_kwargs, extra_kwargs)
    self.assertEquals(instance['a'], '1')
    self.assertEquals(instance['b'], '2')
    self.assertEquals(instance['c'], '3')

class _TstRegisterer(BaseRegisterer):
  def __init__(self, a, b):
    self._a = a
    self._b = b
  def add(self):
    return 'added'
  def remove(self):
    return 'removed'
  def synchronize(self, write):
    return 'synchronized'

class LoadRegistrationPluginTests(unittest.TestCase):
  def test_load_registration_plugin(self):
    plugin_python_path = 'tellapart.aurproxytest.util._TstRegisterer'
    cli_kwargs = ['a=1', 'b=2']
    instance = load_registration_plugin(plugin_python_path, *cli_kwargs)
    self.assertEqual(instance._a, '1')
    self.assertEqual(instance._b, '2')
    self.assertEqual(instance.add(), 'added')
    self.assertEqual(instance.remove(), 'removed')
    self.assertEqual(instance.synchronize(write=True), 'synchronized')

class LoadKlassFactoryTests(KlassFactoryTstBase):
  def test_klass_factory(self):
    self.tst_klass_factory(load_klass_factory)

class LoadKlassPluginTests(unittest.TestCase):
  def test_load_klass_plugin(self):
    def build_klass_dict(klass_field_name='klass'):
      return {
        klass_field_name: '__builtin__.dict',
        'a': '1',
        'b': '2',
      }
    klass_dict = build_klass_dict()
    instance = load_klass_plugin(klass_dict)
    self.assertEquals(instance['a'], '1')
    self.assertEquals(instance['b'], '2')
    extra_kwargs = {'c':'3'}
    instance = load_klass_plugin(klass_dict, **extra_kwargs)
    self.assertEquals(instance['a'], '1')
    self.assertEquals(instance['b'], '2')
    self.assertEquals(instance['c'], '3')
    klass_dict = build_klass_dict('klass2')
    instance = load_klass_plugin(klass_dict, klass_field_name='klass2')
    self.assertEquals(instance['a'], '1')
    self.assertEquals(instance['b'], '2')

class SlugifyTests(unittest.TestCase):
  def test_slugify(self):
    slug_1 = slugify('test')
    slug_2 = slugify('test')
    self.assertEqual(slug_1, slug_2)

    slug_3 = slugify(u'test核')
    self.assertNotIn(u'核', slug_3)

if __name__ == '__main__':
    unittest.main()
