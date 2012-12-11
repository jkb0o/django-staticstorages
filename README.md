ABOUT
-----

Extended staticiles storage.

There is two thing it do with `collectstatic` command:
1. Mark files with versioned hashes
2. Search inside js/css files for links to other static files and
replaces them with marked names.

USAGE
-----

Read oficial docs for basic usage of django staticfiles.
```python
# file: settings.py
STATICFILES_STORAGE = 'django_staticstorages.HashedFilesStorage'
```

It is *important* to use `static` template tag.
```html
{# file: index.html #}
{% load static %}
<html>
<head>
<link rel="stylesheet" href="{% static 'css/main.css' %}">
<script type="text/javascipt" src="{% static js/main.js' %}"></script>
</head>
</html>
```

Difference from djago storage
-----------------------------

Django's CachedFilesStorage do not process JS, and there is no way
to extend it with another processors (plovr configs for example)
