import zlib

from django import template
from django.conf import settings
from .. import utils
register = template.Library()

@register.filter
def thumb(file, args ):
    if not file:
        return ''
    url = file.file
    # Just to ease on crc32, let's trim the file name
    i = zlib.crc32(url[len(settings.AWS_PREFIX):]) % 6 + 1
    url = url.replace(settings.AWS_PREFIX, '%s%s/' % (settings.THUMBNAIL_SERVICE, args))
    if not settings.ON_PRODUCTION_SERVER:
        url = '%s?domain=%s' % (url, settings.AWS_PREFIX[7:-1])
    return url.replace('http://', 'http://m%s.' % i)

@register.filter
def render_thumb( file, args ):
    if not file:
        return ''
    url = thumb(file, args)
    return utils.get_render_string_by_extension(url, {'file': url, 'name':file.name}, True)

