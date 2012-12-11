# -*- encoding: utf-8 -*-
from __future__ import with_statement

if __name__ == '__main__':
    import os
    os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

import codecs
import os
import posixpath
import shutil
import sys
import tempfile
import warnings
from StringIO import StringIO

from django.template import loader, Context
from django.conf import settings
from django.core.cache.backends.base import BaseCache, CacheKeyWarning
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.encoding import smart_unicode
from django.utils.functional import empty
from django.utils._os import rmtree_errorhandler

from django.contrib.staticfiles import finders, storage

TEST_ROOT = os.path.dirname(__file__)
from django.contrib.staticfiles.management.commands.collectstatic import Command as CollectstaticCommand


class BaseStaticFilesTestCase(object):
    """
    Test case with a couple utility assertions.
    """
    def setUp(self):
        # Clear the cached default_storage out, this is because when it first
        # gets accessed (by some other test), it evaluates settings.MEDIA_ROOT,
        # since we're planning on changing that we need to clear out the cache.
        default_storage._wrapped = empty
        storage.staticfiles_storage._wrapped = empty

        testfiles_path = os.path.join(TEST_ROOT, 'app', 'static', 'test')
        # To make sure SVN doesn't hangs itself with the non-ASCII characters
        # during checkout, we actually create one file dynamically.
        self._nonascii_filepath = os.path.join(testfiles_path, u'fi\u015fier.txt')
        with codecs.open(self._nonascii_filepath, 'w', 'utf-8') as f:
            f.write(u"fi\u015fier in the app dir")
        # And also create the stupid hidden file to dwarf the setup.py's
        # package data handling.
        self._hidden_filepath = os.path.join(testfiles_path, '.hidden')
        with codecs.open(self._hidden_filepath, 'w', 'utf-8') as f:
            f.write("should be ignored")
        self._backup_filepath = os.path.join(
            TEST_ROOT, 'project', 'documents', 'test', 'backup~')
        with codecs.open(self._backup_filepath, 'w', 'utf-8') as f:
            f.write("should be ignored")

    def tearDown(self):
        os.unlink(self._nonascii_filepath)
        os.unlink(self._hidden_filepath)
        os.unlink(self._backup_filepath)

    def assertFileContains(self, filepath, text):
        self.assertIn(text, self._get_file(smart_unicode(filepath)),
                        u"'%s' not in '%s'" % (text, filepath))

    def assertFileNotFound(self, filepath):
        self.assertRaises(IOError, self._get_file, filepath)

    def render_template(self, template, **kwargs):
        if isinstance(template, basestring):
            template = loader.get_template_from_string(template)
        return template.render(Context(kwargs)).strip()

    def static_template_snippet(self, path):
        return "{%% load static from staticfiles %%}{%% static '%s' %%}" % path

    def assertStaticRenders(self, path, result, **kwargs):
        template = self.static_template_snippet(path)
        self.assertEqual(self.render_template(template, **kwargs), result)

    def assertStaticRaises(self, exc, path, result, **kwargs):
        self.assertRaises(exc, self.assertStaticRenders, path, result, **kwargs)


class BaseCollectionTestCase(BaseStaticFilesTestCase):
    """
    Tests shared by all file finding features (collectstatic,
    findstatic, and static serve view).

    This relies on the asserts defined in BaseStaticFilesTestCase, but
    is separated because some test cases need those asserts without
    all these tests.
    """
    def setUp(self):
        super(BaseCollectionTestCase, self).setUp()
        self.old_root = settings.STATIC_ROOT
        settings.STATIC_ROOT = tempfile.mkdtemp('djangotmp')
        self.run_collectstatic()
        # Use our own error handler that can handle .svn dirs on Windows
        self.addCleanup(shutil.rmtree, settings.STATIC_ROOT,
                        ignore_errors=True, onerror=rmtree_errorhandler)

    def tearDown(self):
        settings.STATIC_ROOT = self.old_root
        super(BaseCollectionTestCase, self).tearDown()

    def run_collectstatic(self, **kwargs):
        call_command('collectstatic', interactive=False, verbosity='0',
                     ignore_patterns=['*.ignoreme'], **kwargs)

    def _get_file(self, filepath):
        assert filepath, 'filepath is empty.'
        filepath = os.path.join(settings.STATIC_ROOT, filepath)
        with codecs.open(filepath, "r", "utf-8") as f:
            return f.read()


class TestCollectionCachedStorage(BaseCollectionTestCase,
        BaseStaticFilesTestCase, TestCase):
    """
    Tests for the Cache busting storage
    """
    def cached_file_path(self, path):
        fullpath = self.render_template(self.static_template_snippet(path))
        return fullpath.replace(settings.STATIC_URL, '')

    def test_template_tag_return(self):
        """
        Test the CachedStaticFilesStorage backend.
        """
        self.assertStaticRaises(ValueError,
                                "does/not/exist.png",
                                "/static/does/not/exist.png")
        self.assertStaticRenders("test/file.txt",
                                 "/static/test/file.ea5bccaf16d5.txt")
        self.assertStaticRenders("styles.css",
                                 "/static/styles.93b1147e8552.css")
        self.assertStaticRenders("path/",
                                 "/static/path/")
        self.assertStaticRenders("path/?query",
                                 "/static/path/?query")

    def test_template_tag_simple_content(self):
        relpath = self.cached_file_path("styles.css")
        self.assertEqual(relpath, "styles.93b1147e8552.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertNotIn("cached/other.css", content)
            self.assertIn("other.d41d8cd98f00.css", content)

    def test_path_with_querystring(self):
        relpath = self.cached_file_path("styles.css?spam=eggs")
        self.assertEqual(relpath,
                         "styles.93b1147e8552.css?spam=eggs")
        with storage.staticfiles_storage.open(
                "styles.93b1147e8552.css") as relfile:
            content = relfile.read()
            self.assertNotIn("other.css", content)
            self.assertIn("other.d41d8cd98f00.css", content)

    def test_path_with_fragment(self):
        relpath = self.cached_file_path("styles.css#eggs")
        self.assertEqual(relpath, "styles.93b1147e8552.css#eggs")
        with storage.staticfiles_storage.open(
                "styles.93b1147e8552.css") as relfile:
            content = relfile.read()
            self.assertNotIn("other.css", content)
            self.assertIn("other.d41d8cd98f00.css", content)

    def test_path_with_querystring_and_fragment(self):
        relpath = self.cached_file_path("css/fragments.css")
        self.assertEqual(relpath, "css/fragments.75433540b096.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertIn('fonts/font.a4b0478549d0.eot?#iefix', content)
            self.assertIn('fonts/font.b8d603e42714.svg#webfontIyfZbseF', content)
            self.assertIn('data:font/woff;charset=utf-8;base64,d09GRgABAAAAADJoAA0AAAAAR2QAAQAAAAAAAAAAAAA', content)
            self.assertIn('#default#VML', content)

    def test_template_tag_absolute(self):
        relpath = self.cached_file_path("absolute.css")
        self.assertEqual(relpath, "absolute.b094e4c60b0e.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertNotIn("/static/styles.css", content)
            self.assertIn("/static/styles.93b1147e8552.css", content)
            self.assertIn('/static/img/relative.acae32e4532b.png', content)

    def test_template_tag_denorm(self):
        relpath = self.cached_file_path("denorm.css")
        self.assertEqual(relpath, "denorm.7394833810b4.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertNotIn("..///styles.css", content)
            self.assertIn("../styles.93b1147e8552.css", content)
            self.assertNotIn("url(img/relative.png )", content)
            self.assertIn('url("img/relative.acae32e4532b.png', content)

    def test_template_tag_relative(self):
        relpath = self.cached_file_path("relative.css")
        self.assertEqual(relpath, "relative.2f2aea7a52dd.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertNotIn("./styles.css", content)
            self.assertNotIn('@import "styles.css"', content)
            self.assertNotIn('url(img/relative.png)', content)
            self.assertIn('url("img/relative.acae32e4532b.png")', content)
            self.assertIn("styles.93b1147e8552.css", content)

    def test_template_tag_deep_relative(self):
        relpath = self.cached_file_path("css/window.css")
        self.assertEqual(relpath, "css/window.9db38d5169f3.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            content = relfile.read()
            self.assertNotIn('url(img/window.png)', content)
            self.assertIn('url("img/window.acae32e4532b.png")', content)

    def test_template_tag_url(self):
        relpath = self.cached_file_path("url.css")
        self.assertEqual(relpath, "url.615e21601e4b.css")
        with storage.staticfiles_storage.open(relpath) as relfile:
            self.assertIn("https://", relfile.read())

    def test_cache_invalidation(self):
        name = "styles.css"
        hashed_name = "styles.93b1147e8552.css"
        # check if the cache is filled correctly as expected
        cache_key = storage.staticfiles_storage.cache_key(name)
        cached_name = storage.staticfiles_storage.cache.get(cache_key)
        self.assertEqual(self.cached_file_path(name), cached_name)
        # clearing the cache to make sure we re-set it correctly in the url method
        storage.staticfiles_storage.cache.clear()
        cached_name = storage.staticfiles_storage.cache.get(cache_key)
        self.assertEqual(cached_name, None)
        self.assertEqual(self.cached_file_path(name), hashed_name)
        cached_name = storage.staticfiles_storage.cache.get(cache_key)
        self.assertEqual(cached_name, hashed_name)

    def test_post_processing(self):
        """Test that post_processing behaves correctly.

        Files that are alterable should always be post-processed; files that
        aren't should be skipped.

        collectstatic has already been called once in setUp() for this testcase,
        therefore we check by verifying behavior on a second run.
        """
        collectstatic_args = {
            'interactive': False,
            'verbosity': '0',
            'link': False,
            'clear': False,
            'dry_run': False,
            'post_process': True,
            'use_default_ignore_patterns': True,
            'ignore_patterns': ['*.ignoreme'],
        }

        collectstatic_cmd = CollectstaticCommand()
        collectstatic_cmd.set_options(**collectstatic_args)
        stats = collectstatic_cmd.collect()
        self.assertTrue(os.path.join('css', 'window.css') in stats['post_processed'])
        self.assertTrue(os.path.join('css', 'img', 'window.png') in stats['unmodified'])

    def test_cache_key_memcache_validation(self):
        """
        Handle cache key creation correctly, see #17861.
        """
        name = "/some crazy/long filename/ with spaces Here and ?#%#$/other/stuff/some crazy/long filename/ with spaces Here and ?#%#$/other/stuff/some crazy/long filename/ with spaces Here and ?#%#$/other/stuff/some crazy/long filename/ with spaces Here and ?#%#$/other/stuff/some crazy/long filename/ with spaces Here and ?#%#$/other/stuff/some crazy/" + chr(22) + chr(180)
        cache_key = storage.staticfiles_storage.cache_key(name)
        self.save_warnings_state()
        cache_validator = BaseCache({})
        warnings.filterwarnings('error', category=CacheKeyWarning)
        cache_validator.validate_key(cache_key)
        self.restore_warnings_state()
        self.assertEqual(cache_key, 'staticfiles:e95bbc36387084582df2a70750d7b351')


if __name__ == '__main__':
    import os
    sys.path.append('..')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
    t = TestCollectionCachedStorage('setUp')
    print t.cached_file_path('absolute.css')
