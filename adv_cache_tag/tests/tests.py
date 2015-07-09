import hashlib
import zlib

from datetime import datetime

from django.conf import settings

from adv_cache_tag.compat import get_cache, pickle, template
from adv_cache_tag.tag import CacheTag

from .compat import make_template_fragment_key, override_settings, SafeText, TestCase


# Force some settings to not depend on the external ones
@override_settings(

    # Force using memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'default-cache',
        },
        'foo': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'foo-cache',
        },
    },

    # Used to compose RAW tags
    SECRET_KEY = 'm-92)2et+&&m5f&#jld7-_1qanq*n9!z90xc@+wx6y8d6y#w6t',

    # Reset default config
    ADV_CACHE_VERSIONING = False,
    ADV_CACHE_COMPRESS = False,
    ADV_CACHE_COMPRESS_SPACES= False,
    ADV_CACHE_INCLUDE_PK = False,
    ADV_CACHE_BACKEND = 'default',
    ADV_CACHE_VERSION = '',
)
class BasicTestCase(TestCase):
    """First basic test case to be able to test python/django compatibility."""

    @classmethod
    def reload_config(cls):
        """Resest the ``CacheTag`` configuration from current settings"""
        CacheTag._meta.versioning = getattr(settings, 'ADV_CACHE_VERSIONING', False)
        CacheTag._meta.compress = getattr(settings, 'ADV_CACHE_COMPRESS', False)
        CacheTag._meta.compress_spaces = getattr(settings, 'ADV_CACHE_COMPRESS_SPACES', False)
        CacheTag._meta.include_pk = getattr(settings, 'ADV_CACHE_INCLUDE_PK', False)
        CacheTag._meta.cache_backend = getattr(settings, 'ADV_CACHE_BACKEND', 'default')
        CacheTag._meta.internal_version = getattr(settings, 'ADV_CACHE_VERSION', '')

        # generate a token for this site, based on the secret_key
        CacheTag.RAW_TOKEN = 'RAW_' + hashlib.sha1(
            'RAW_TOKEN_SALT1' + hashlib.sha1(
                'RAW_TOKEN_SALT2' + settings.SECRET_KEY
            ).digest()
        ).hexdigest()

        # tokens to use around the already parsed parts of the cached template
        CacheTag.RAW_TOKEN_START = template.BLOCK_TAG_START + CacheTag.RAW_TOKEN + \
                                   template.BLOCK_TAG_END
        CacheTag.RAW_TOKEN_END = template.BLOCK_TAG_START + 'end' + CacheTag.RAW_TOKEN + \
                                 template.BLOCK_TAG_END

    def setUp(self):
        """Clean stuff and create an object to use in templates, and some counters."""
        super(BasicTestCase, self).setUp()

        # Clear the cache
        for cache_name in settings.CACHES:
            get_cache(cache_name).clear()

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        # And an object to cache in template
        self.obj = {
            'pk': 42,
            'name': 'foobar',
            'get_name': self.get_name,
            'get_foo': self.get_foo,
            'updated_at': datetime(2015, 10, 27, 0, 0, 0),
        }

        # To count the number of calls of ``get_name`` and ``get_foo``.
        self.get_name_called = 0
        self.get_foo_called = 0

    def get_name(self):
        """Called in template when asking for ``obj.get_name``."""
        self.get_name_called += 1
        return self.obj['name']

    def get_foo(self):
        """Called in template when asking for ``obj.get_foo``."""
        self.get_foo_called += 1
        return 'foo %d' % self.get_foo_called

    def tearDown(self):
        """Clear caches at the end."""

        for cache_name in settings.CACHES:
            get_cache(cache_name).clear()

        super(BasicTestCase, self).tearDown()

    @classmethod
    def tearDownClass(cls):
        """At the very end of all theses tests, we reload the CacheTag config."""

        # Reset CacheTag config after the end of ``override_settings``
        cls.reload_config()

        super(BasicTestCase, cls).tearDownClass()

    def render(self, template_text, context_dict=None):
        """Utils to render a template text with a context given as a dict."""
        if context_dict is None:
            context_dict = {'obj': self.obj}
        return template.Template(template_text).render(template.Context(context_dict))

    def assertStripEqual(self, first, second):
        """Like ``assertEqual`` for strings, but after calling ``strip`` on both arguments."""
        if first:
            first = first.strip()
        if second:
            second = second.strip()

        self.assertEqual(first, second)

    def assertNotStripEqual(self, first, second):
        """Like ``assertNotEqual`` for strings, but after calling ``strip`` on both arguments."""
        if first:
            first = first.strip()
        if second:
            second = second.strip()

        self.assertNotEqual(first, second)

    def test_default_cache(self):
        """This test is only to validate the testing procedure."""

        expected = "foobar"

        t = """
            {% load cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        self.assertStripEqual(get_cache('default').get(key), expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    def test_adv_cache(self):
        """Test default behaviour with default settings."""

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # But it should NOT be the exact content as adv_cache_tag adds a version
        self.assertNotStripEqual(get_cache('default').get(key), expected)

        # It should be the version from `adv_cache_tag`
        cache_expected = u"0.1::\n                foobar"
        self.assertStripEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_VERSIONING = True,
    )
    def test_versioning(self):
        """Test with ``ADV_CACHE_VERSIONING`` set to ``True``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache

        # ``obj.updated_at`` is not in the key anymore, serving as the object version
        key = make_template_fragment_key('test_cached_template', vary_on=[self.obj['pk']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.a1d0c6e83f027327d8461063f4ac58a6')

        # It should be in the cache, with the ``updated_at`` in the version
        cache_expected = u"0.1::2015-10-27 00:00:00::\n                foobar"
        self.assertStripEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

        # We can update the date
        self.obj['updated_at'] = datetime(2015, 10, 28, 0, 0, 0)

        # Render with the new date, we should miss the cache because of the new "version
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 2)  # One more

        # It should be in the cache, with the new ``updated_at`` in the version
        cache_expected = u"0.1::2015-10-28 00:00:00::\n                foobar"
        self.assertStripEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 2)  # Still 2

    @override_settings(
        ADV_CACHE_INCLUDE_PK = True,
    )
    def test_primary_key(self):
        """Test with ``ADV_CACHE_INCLUDE_PK`` set to ``True``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache

        # We add the pk as a part to the fragment name
        key = make_template_fragment_key('test_cached_template.%s' % self.obj['pk'],
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.42.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache
        cache_expected = u"0.1::\n                foobar"
        self.assertStripEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_COMPRESS_SPACES = True,
    )
    def test_space_compression(self):
        """Test with ``ADV_CACHE_COMPRESS_SPACES`` set to ``True``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache, with only one space instead of many white spaces
        cache_expected = u"0.1:: foobar "
        # Test with ``assertEqual``, not ``assertStripEqual``
        self.assertEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_COMPRESS = True,
    )
    def test_compression(self):
        """Test with ``ADV_CACHE_COMPRESS`` set to ``True``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        # We don't use new lines here because too complicated to set empty lines with only
        # spaces in a docstring with we'll have to compute the compressed version
        t = "{% load adv_cache %}{% cache 1 test_cached_template obj.pk obj.updated_at %}" \
            "  {{ obj.get_name }}  {% endcache %}"

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache, compressed
        # We use ``SafeText`` as django does in templates
        compressed = zlib.compress(pickle.dumps(SafeText(u"  foobar  ")))
        cache_expected = '0.1::' + compressed
        # Test with ``assertEqual``, not ``assertStripEqual``
        self.assertEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_COMPRESS = True,
        ADV_CACHE_COMPRESS_SPACES = True,
    )
    def test_full_compression(self):
        """Test with ``ADV_CACHE_COMPRESS`` and ``ADV_CACHE_COMPRESS_SPACES`` set to ``True``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache, compressed
        # We DON'T use ``SafeText`` as in ``test_compression`` because with was converted back
        # to a real string when removing spaces
        compressed = zlib.compress(pickle.dumps(u" foobar "))
        cache_expected = '0.1::' + compressed
        # Test with ``assertEqual``, not ``assertStripEqual``
        self.assertEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_BACKEND = 'foo',
    )
    def test_cache_backend(self):
        """Test with ``ADV_CACHE_BACKEND`` to another value than ``default``."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache
        cache_expected = u"0.1::\n                foobar"

        # But not in the ``default`` cache
        self.assertIsNone(get_cache('default').get(key))

        # But in the ``foo`` cache
        self.assertStripEqual(get_cache('foo').get(key), cache_expected)

        # Render a second time, should hit the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1

    @override_settings(
        ADV_CACHE_COMPRESS_SPACES = True,
    )
    def test_partial_cache(self):
        """Test the ``nocache`` templatetag."""

        # Reset CacheTag config with default value (from the ``override_settings``)
        self.reload_config()

        expected = "foobar  foo 1  !!"

        t = """
            {% load adv_cache %}
            {% cache 1 test_cached_template obj.pk obj.updated_at %}
                {{ obj.get_name }}
                {% nocache %}
                    {{ obj.get_foo }}
                {% endnocache %}
                !!
            {% endcache %}
        """

        # Render a first time, should miss the cache
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)
        self.assertEqual(self.get_foo_called, 1)

        # Now the rendered template should be in cache
        key = make_template_fragment_key('test_cached_template',
                                         vary_on=[self.obj['pk'], self.obj['updated_at']])
        self.assertEqual(
            key, 'template.cache.test_cached_template.0cac9a03d5330dd78ddc9a0c16f01403')

        # It should be in the cache, with the RAW part
        cache_expected = u"0.1:: foobar {%endRAW_947b3fc9bc5fb05cd2f03bb559ad06b2916b8add%} " \
                         u"{{obj.get_foo}} {%RAW_947b3fc9bc5fb05cd2f03bb559ad06b2916b8add%} !! "
        self.assertStripEqual(get_cache('default').get(key), cache_expected)

        # Render a second time, should hit the cache but not for ``get_foo``
        expected = "foobar  foo 2  !!"
        self.assertStripEqual(self.render(t), expected)
        self.assertEqual(self.get_name_called, 1)  # Still 1
        self.assertEqual(self.get_foo_called, 2)  # One more call
