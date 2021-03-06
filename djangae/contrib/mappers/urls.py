from django.conf.urls import patterns
from djangae.utils import djangae_webapp


try:
    from mapreduce.main import create_handlers_map
    wrapped_urls = ((url_re.replace('.*/', '^', 1), djangae_webapp(func)) for url_re, func in create_handlers_map())
except ImportError as e:
    wrapped_urls = []


urlpatterns = patterns('', *wrapped_urls)
