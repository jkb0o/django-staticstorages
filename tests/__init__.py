import os
import sys
import unittest
sys.path.append('./tests')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'settings')


from django.test.utils import setup_test_environment
from django.core.management import call_command
call_command('syncdb', noinput=True)
setup_test_environment()


unittest.TestLoader().loadTestsFromName('test_hashstorage')
