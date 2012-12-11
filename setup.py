from setuptools import setup, find_packages

DESCRIPTION = 'Django staticfiles finders with ability to filter files'
try:
    LONG_DESCRIPTION = open('README.rst').read()
except:
    LONG_DESCRIPTION = None

setup(
    name='django-staticstorages',
    version='0.1',
    packages=find_packages(),
    author='Yasha Borevich',
    author_email='j.borevich@gmail.com',
    url='http://github.com/jjay/django-staticstorages',
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    test_suite='tests',
    platforms='any',
)
