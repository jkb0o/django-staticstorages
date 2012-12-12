ABOUT
-----

Extended staticiles storage.

There is two thing it do with `collectstatic` command:


1.  Mark files with versioned hashes
2.  Search inside js/css files for links to other static files and
replaces them with marked names.


Why?
----

While css files are standardized, patterns 
like url("...") or @import '...' is simple to process,
and it is implemented by django's CachedFilesStorage. 

It is often useful to have ability to make
versioned files and to access them not only from css,
but also from js files. 

This django plugin is an attemt to do this.

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

CSS & JS names normalization
----------------------------

When you run `collectstatic` command, storage try to parse urls 
in js and css files and replace them whith versioned *abolute* path.
For example, if you declare url likt this `url('../img/button.png')` 
it will be replaced with something like this: `url('/statci/img/button.cf56ab17.png')`,
where `cf56ab17` is md5 of original file.

For css files storage backend process both `url('path/to/resource')`,
`@import ('path/to/resource')` and `@import url('path/to/resource')` with
single quotes, double quotes and without quotes at all. 

There is an example of css declaration
```css
/* file $DJANGO_PROJECT/css/defaults/main.css */
body { 
    /* replaces with ... url("/static/img/bg.fh0101ab.jpg") */
    background: transparent url('../..//img/bg.jpg'); 

    /* 
     * absolute path, replaces with ... url("/static/img/bg.fh0101ab.jpg"))
     * look, how unquoted url replaced with true variant
     */
    background: transparent url(/static/img/bg.jpg)

    /* http[s], data, // urls does not processed */
    background: transparent url('http://hopage.com/static/image.jpg')
}
```


There is a way to access to your static files from javascript code. 
Any string variable with patternt similar to
`"url('path/to/resource')"` will be replaced with actual path.

There ia an example:
```javascript

// it will be replaced with "/static/img/smile.afaf1024.png"
var image_src = 'url("../img/smile.png")'
```

Customization
-------------

<totally incomplete docs>

It is simple to customize the behaviour of staticstorages.
The best way to understand how to do this, is to read
the source code.

You can totally redefine the behaviour of staticstorages by
redefining STATICFILES_HASHED_PROCESSORS.

If you only need to define custom js template, you can 
specify STATIC_JSPROCESSOR_TEMPLATE settings.


Difference from djago storage
-----------------------------

Django's CachedFilesStorage do not process JS, and there is no way
to extend it with another processors (plovr configs for example).
It is also has some bugs with CachedFilesStorage, which statocstorages
fixes.
