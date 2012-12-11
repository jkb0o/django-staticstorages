import fnmatch
import functools
import hashlib
import json
import os.path
import posixpath
import re
from urllib import unquote
from urlparse import urlsplit, urlunsplit, urldefrag

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import get_storage_class
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.utils.encoding import smart_str, force_unicode


DEFAULT_HASHED_PROCESSORS = (
    'django_staticstorages.JsProcessor',
    'django_staticstorages.CssProcessor',
)

class BaseProcessor(object):
    def __init__(self, backend):
        self.backend = backend

    def _process_url(self, name, url):
        # Completely ignore http(s) prefixed URLs,
        # fragments and data-uri URLs
        if url.startswith(('#', 'http:', 'https:', 'data:')):
            return url

        name_parts = name.split(os.sep)
        if len(name_parts) == 1:
            name_parts = ['']
        # Using posix normpath here to remove duplicates
        url = posixpath.normpath(url)
        url_parts = url.split('/')
        parent_level, sub_level = url.count('..'), url.count('/')
        if url.startswith('/'):
            sub_level -= 1
            url_parts = url_parts[1:]
        if parent_level or not url.startswith('/'):
            start, end = parent_level + 1, parent_level
        else:
            if sub_level:
                if sub_level == 1:
                    parent_level -= 1
                start, end = parent_level, 1
            else:
                start, end = 1, sub_level - 1
        joined_result = '/'.join(name_parts[:-start] + url_parts[end:]).strip('/')
        hashed_url = self.backend.url(unquote(joined_result), force=True)
        file_name = hashed_url.split('/')[-1:]
        relative_url = '/'.join(url.split('/')[:-1] + file_name)

        # Return the hashed version to the file
        return unquote(relative_url)


class JsProcessor(BaseProcessor):
    filepattern = '*.js'
    pattern = re.compile(getattr(settings, 'STATIC_JSPROCESSOR_TEMPLATE',
        r"STATIC.url\(\s*(?P<d>['\"])(?P<content>.*?)(?P=d)\s*\)"))

    def __init__(self, backend):
        self.backend = backend

    def process(self, name, content):
        return self.pattern.sub(functools.partial(self._process, name), content)

    def _process(self, name, match):
        url = match.group('content')
        url = self._process_url(url)
        return '"%s"' % url

class CssProcessor(BaseProcessor):
    filepattern = '*.css'
    url_pattern = re.compile(r"""(url\(['"]{0,1}\s*(.*?)["']{0,1}\))""")
    import_pattern = re.compile(r"""(@import\s*["']\s*(.*?)["'])""")

    def process(self, name, content):
        content = self.url_pattern.sub(functools.partial(self.do_process_url, name), content)
        content = self.import_pattern.sub(functools.partial(self.do_process_import, name), content)
        return content

    def do_process_url(self, name, match):
        url = self._process_url(name, match.group(2))
        return 'url("%s")' % url

    def do_process_import(self, match, name):
        url = self._process_url(name, match.group(2))
        return '@import "%s"' % url


class HashedCache(dict):
    
    def __init__(self):
        self.filename = getattr(settings, 'STATIC_CACHE_FILE', 'static.json')
        try:
            self.update(json.load(open(self.filename, 'r')))
        except (IOError, ValueError):
            pass

    def set(self, key, value):
        self[key] = value
        self.save()

    def set_many(self, values):
        self.update(values)
        self.save()

    def save(self):
        with open(self.filename, 'w') as sf:
            json.dump(self, sf)
        
        

    
class HashedFilesStorage(StaticFilesStorage):

    def __init__(self, *args, **kwargs):
        self.cache = HashedCache()
        super(HashedFilesStorage, self).__init__(*args, **kwargs)

    def hashed_name(self, name, content=None):
        parsed_name = urlsplit(unquote(name))
        clean_name = parsed_name.path.strip()
        if content is None:
            if not self.exists(clean_name):
                raise ValueError("The file '%s' could not be found with %r." %
                                 (clean_name, self))
            try:
                content = self.open(clean_name)
            except IOError:
                # Handle directory paths and fragments
                return name
        path, filename = os.path.split(clean_name)
        root, ext = os.path.splitext(filename)
        # Get the MD5 hash of the file
        md5 = hashlib.md5()
        for chunk in content.chunks():
            md5.update(chunk)
        md5sum = md5.hexdigest()[:12]
        hashed_name = os.path.join(path, u"%s.%s%s" %
                                   (root, md5sum, ext))
        unparsed_name = list(parsed_name)
        unparsed_name[2] = hashed_name
        # Special casing for a @font-face hack, like url(myfont.eot?#iefix")
        # http://www.fontspring.com/blog/the-new-bulletproof-font-face-syntax
        if '?#' in name and not unparsed_name[3]:
            unparsed_name[2] += '?'
        return urlunsplit(unparsed_name)
    
    def cache_key(self, name):
        return u'staticfiles:%s' % hashlib.md5(smart_str(name)).hexdigest()
    
    def url(self, name, force=False):
        """
        Returns the real URL in DEBUG mode.
        """
        if settings.DEBUG and not force:
            hashed_name, fragment = name, ''
        else:
            clean_name, fragment = urldefrag(name)
            if urlsplit(clean_name).path.endswith('/'):  # don't hash paths
                hashed_name = name
            else:
                cache_key = self.cache_key(name)
                hashed_name = self.cache.get(cache_key)
                if hashed_name is None:
                    hashed_name = self.hashed_name(clean_name).replace('\\', '/')
                    # set the cache if there was a miss
                    # (e.g. if cache server goes down)
                    self.cache.set(cache_key, hashed_name)

        final_url = super(HashedFilesStorage, self).url(hashed_name)

        # Special casing for a @font-face hack, like url(myfont.eot?#iefix")
        # http://www.fontspring.com/blog/the-new-bulletproof-font-face-syntax
        query_fragment = '?#' in name  # [sic!]
        if fragment or query_fragment:
            urlparts = list(urlsplit(final_url))
            if fragment and not urlparts[4]:
                urlparts[4] = fragment
            if query_fragment and not urlparts[3]:
                urlparts[2] += '?'
            final_url = urlunsplit(urlparts)

        return unquote(final_url)
    
    def post_process(self, paths, dry_run=False, **options):
        # don't even dare to process the files if we're in dry run mode
        if dry_run:
            return

        self.cache.clear()

        # where to store the new paths
        hashed_paths = {}

        processors = getattr(settings, 'STATICFILES_HASHED_PROCESSORS', 
            DEFAULT_HASHED_PROCESSORS)
        processors = [get_storage_class(p)(self) for p in processors]
        processors = sorted(processors, 
            key=lambda p: len(p.filepattern), reverse=True)
        

        
        # then sort the files by the directory level
        path_level = lambda name: len(name.split(os.sep))
        for name in sorted(paths.keys(), key=path_level, reverse=True):

            # use the original, local file, not the copied-but-unprocessed
            # file, which might be somewhere far away, like S3
            storage, path = paths[name]
            for processor in processors:
                if fnmatch.fnmatch(path, processor.filepattern):
                    break
            else:
                processor = None

            with storage.open(path) as original_file:

                # generate the hash with the original content, even for
                # adjustable files.
                hashed_name = self.hashed_name(name, original_file)

                # then get the original's file content..
                if hasattr(original_file, 'seek'):
                    original_file.seek(0)

                hashed_file_exists = self.exists(hashed_name)
                processed = False

                # ..to apply each replacement pattern to the content
                if processor:
                    content = original_file.read()
                    content = processor.process(name, content)
                    if hashed_file_exists:
                        self.delete(hashed_name)

                    # then save the processed result
                    content_file = ContentFile(smart_str(content))
                    saved_name = self._save(hashed_name, content_file)
                    hashed_name = force_unicode(saved_name.replace('\\', '/'))
                    processed = True
                else:
                    # or handle the case in which neither processing nor
                    # a change to the original file happened
                    if not hashed_file_exists:
                        processed = True
                        saved_name = self._save(hashed_name, original_file)
                        hashed_name = force_unicode(saved_name.replace('\\', '/'))

                # and then set the cache accordingly
                hashed_paths[self.cache_key(name)] = hashed_name
                yield name, hashed_name, processed

        # Finally set the cache
        self.cache.set_many(hashed_paths)
