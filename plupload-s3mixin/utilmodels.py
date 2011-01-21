# Python imports
import mimetypes
import os
import functools

# AppEngine imports

# Django imports
from django.http import HttpResponseServerError
from django.template import Context, Template, RequestContext
from django.http import HttpResponse
from django.forms.util import flatatt
from django.utils.safestring import mark_safe
from django.utils import simplejson
from django.core.signals import request_finished

# Local imports

# Constants
RENDER_MIMES = {
                'text/css': '<link rel="stylesheet" href="%(file)s" type="text/css" %(attrs)s />',
                'application/x-javascript': '<script %(attrs)s type="text/javascript" src="%(file)s" alt="%(name)s"></script>',
                'image': '<img %(attrs)s src="%(file)s" alt="%(name)s" />',
                'application/x-shockwave-flash': '''<div id="%(file_base)s" %(attrs)s>This page requires Flash%(thumb)s</div>
                                    <script type="text/javascript">
                                        swfobject.embedSWF('%(file)s', '%(file_base)s', '100%%', '100%%', '6.0.0');
                                    </script>
                                    ''',
                # DEFAULT
                '*': '<a %(attrs)s href="%(file)s">%(name)s</a>', 
                }

VISIBLE_MIMES = ('image', '*')
# Helpers
def get_render_string_by_extension(file_name, params, only_visibles=False):
    """
        renders an HTML tag appropriate for the given file
        
        only_visibles avoids rendering non displayable types like javascript/css while keep displaying swfs/images
        attributes is the HTML attributes of the element
    """
    if '?' in file_name: file_name = file_name[:file_name.index('?')]
    mime_type = mimetypes.guess_type(file_name)[0]
    if not mime_type:
        mime_type = 'application'
    return get_render_string(mime_type, params, only_visibles)

def get_render_string(mime_type, params, only_visibles=False):
    attrs = {}
    if mime_type in RENDER_MIMES:
        render_mime_type = mime_type if not only_visibles or mime_type in VISIBLE_MIMES else '*'
    else:
        # Loop for identifying the major type (like 'image')
        for key, value in RENDER_MIMES.items():
            if mime_type.startswith(key):
                render_mime_type = key if not only_visibles or key in VISIBLE_MIMES else '*'
                break
        else: # Not found... we're not sure how to render this mime_type, so we'll just use the default
            render_mime_type = '*'
            
    # Add class attribute to 'visible' mimes
    if only_visibles:
        if render_mime_type=='*':
            c = mime_type.partition('/')[0]
        else: 
            c = render_mime_type.partition('/')[0] if '/' in render_mime_type else render_mime_type 
        if 'class' in attrs:
            if c not in attrs['class']:
                attrs['class'] += ' ' + c
        else:
            attrs['class'] = c
    params['attrs'] = flatatt(attrs)
    if 'thumb' not in params: params['thumb'] = ''
    if 'file_base' not in params: params['file_base'] = os.path.splitext(os.path.basename(params['file']))[0]
    return mark_safe(RENDER_MIMES[render_mime_type] % params)
