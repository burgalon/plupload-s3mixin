# Python imports
import mimetypes
import logging
import time
import base64
import hmac, sha
import os
import zlib
import rfc822
import datetime
import urllib

# AppEngine imports
from google.appengine.api import urlfetch

# Django imports
from django.utils import simplejson
from django.db import models
from django.shortcuts import render_to_response, get_object_or_404
from django import forms
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
import django.dispatch
from django.conf import settings

from mediagenerator.utils import media_url
from djangotoolbox.http import JSONResponse

s3policy_request = django.dispatch.Signal(providing_args=['prefix'])
SUPPORTED_FORMATS = 'jpg,png,gif,css,html,js,pdf,swf,ico,mp3'

class S3FileWidget(forms.HiddenInput):
    is_hidden = False

    class Meta:
        abstract = True

    def __init__(self, prefix, type, auto_upload=False, required=True, allowed_types=SUPPORTED_FORMATS, *args, **kwargs):
        self.prefix = prefix
        self.type = type
        self.auto_upload = auto_upload
        self.required = required
        self.allowed_types = allowed_types
        super(forms.HiddenInput, self).__init__(*args, **kwargs)

    def render(self, name, value, attrs=None):
        # save parameter for later use by inline()
        self.attrs['id'] = attrs['id']
        self.name = name
        output = super(S3FileWidget, self).render(name, value, attrs)
        if value:
            link = '<a class="new-window" href="%s">%s</a>' % (value, os.path.basename(value))
            output += mark_safe(u'''
                <div id="%s_preview">
                    %s
                </div>''' % (attrs['id'],
                            link,
                            ))
        return output + mark_safe(u'''
            <div id="%(id)s-container" class="upload-container"><a href="#" id="%(id)s-upload">Select File</a></div>
            <div id="%(id)s-filelist"></div>''' %
            {'id': self.attrs['id']})

    def javascript(self):
        return mark_safe(u'''
                var uploader =  new plupload.Uploader({
                    runtimes : 'flash',
                    use_query_string: false,
                    multipart: true,
                    url: '%(aws_prefix)s',
                    multi_selection: true,
                    form: $('#%(id)s').closest('form'),
                    signature_url: '%(signature_url)s',
                    browse_button : '%(id)s-upload',
                    container : '%(id)s-container',
                    filelistelement: $('#%(id)s-filelist'),
                    max_file_size : '%(max_file_size)s',
                    flash_swf_url : '%(swf_url)s',
                    file_data_name: 'file',
                    file_input_name: '%(name)s',
                    filters : [
                        {title : "Supported files (%(allowed_types)s)", extensions : "%(allowed_types)s"}
                    ],
		            resize : {width : 1920, height : 1080, quality : 90}
                });
                uploader.init();
                uploader.bind('FilesAdded', onPluploadFilesAdded);
                uploader.bind('UploadFile', onPluploadUploadFile);
                uploader.bind('UploadProgress', onPluploadUploadProgress);
                uploader.bind('Error', onPluploadError);
                uploader.bind('FileUploaded', onPluploadFileUploaded);
                '''
                % {
                    'signature_url': reverse('s3policy', args=[self.prefix, self.type]),
                   # swf: '%ss3_upload.swf',
                    'swf_url': media_url('js/plupload/plupload.flash.swf'),
                   # $('#%s').val('');
                    'id': self.attrs['id'],
                    # /* auto_upload */
                    'auto_upload': 'true' if self.auto_upload else 'false',
                   # document.getElementById('%s').value='%s' + '%s' + filename;
                    'aws_prefix': settings.AWS_PREFIX,
                   # document.getElementById('%s').value='%s' + '%s' + filename;
                    'prefix': '%s/%s/' % (self.prefix, time.time()),
                    'name': self.name,
                    'allowed_types': self.allowed_types,
                    'max_file_size': settings.AWS_MAX_FILE_SIZE,
                   } )

class S3Mixin(models.Model):
    """A mixin class that gives thumbnail services for files uploaded to Amazon S3
    Also on delete it will delete the object from S3
    """
#    file = models.URLField(null=True, verify_exists=False, max_length=1000)
    file = models.CharField(null=True, max_length=300)
    file_thumb = models.CharField(null=True, max_length=300) # TODO: DEPRECATE
    file_data = models.TextField(null=True)

    # Default types to be saved on the server side and not on S3
    SERVER_TYPES = ('.html', '.htm', '.css')
    class Meta:
        abstract = True # important!

    def download_to_server(self):
        """
            Downloads 'file' url to file_data
            Does NOT delete from S3
        """
        if not self.file:
            return
        logging.info('s3mixin tries to fetch %s' % self.file)
        fetch_result = urlfetch.fetch(self.file, follow_redirects=False)
        if fetch_result.status_code != 200:
            logging.info('s3mixin received status_code %s' % fetch_result.status_code)
            raise urlfetch.Error('HTTP status code %s' % fetch_result.status_code)
        self.file_data = fetch_result.content

    def get_aws_connection(self):
        return S3.AWSAuthConnection(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)

    def s3_prefix(self):
        """
        Generate a prefix for the object which is saved
        This should be in accordance with the generated prefix from the Widget above
        """
        return '%s/%s/' % (self.p.id, time.time())

    def upload_data_to_s3(self, data, file_name, content_type=None):
        """
            Helper to upload_file_to_s3 + ....
        """
        self.download_to_server()
        s3_key = self.s3_prefix() + file_name
        logging.info('uploading file_name %s s3_key %s' % (file_name, s3_key))
        if not content_type:
            if not file_name:
                content_type = 'text/plain'
            else:
                content_type = mimetypes.guess_type(file_name)[0]
            # if mimetypes was unable to detect mime, use default
            if not content_type:
                content_type = 'text/plain'

        connection = self.get_aws_connection()
        connection.put(
            settings.AWS_BUCKET,
            s3_key,
            S3.S3Object(data),
            {'x-amz-acl': 'public-read',
             'Content-Type': content_type,
             # Since we have the version prefix, this can stay cached in the browser forever
             'Cache-Control': 'public, max-age=2629743'
                }
        )
        return self.s3name(s3_key)

    def basename(self):
        return os.path.basename(self.file) if self.file else 'file'

    def __unicode__(self):
        return self.basename()

    def s3name(self, basename):
        return settings.AWS_PREFIX + basename

    def upload_file_to_s3(self):
        """
            Uploads file_data to S3
            and delete file_data
        """
        # use 'file' url to generate file name. If not available use some timestamp
        if not self.file_data:
            raise ValueError('no file_data found to upload to S3')
        self.file = self.upload_data_to_s3(self.file_data, self.basename())
        logging.info('updated self.file to %s' % self.file)
        self.file_data = None

    def is_image(self):
        return self.extension().lower() in ('.jpg', '.png', '.gif', '.jpe')

    def size(self):
        return None,None

    def mime_type(self):
        mime = mimetypes.guess_type(self.file)
        return mime[0] if len(mime) else 'text/plain'

    def mime_icon(self):
        return media_url('images/txt.png')

    def extension(self):
        try:
            s,ext = os.path.splitext(os.path.basename(self.file))
        except:
            return ''
        return ext

    def process_file(self, x=None, y=None, x2=None, y2=None):
        """
            1) If given file type is set to be stored at the SERVER, download it
                (like .HTML which is used for server side templates)
                OR if the given file URL is remote
            2) return?! :)
        """
        if not self.file:
            return
        ext = self.extension()
        # If this file type should be stored in the SERVER or a non S3 URL was given
        if ext in self.SERVER_TYPES or not self.file.startswith(settings.AWS_PREFIX):
            self.download_to_server()
            if ext not in self.SERVER_TYPES:
                self.upload_file_to_s3()
        else:
            self.file_data = None

    def save(self, suppressFileDelete=False):
        """ Helper services before save
        """
        if self.pk:
            prev_entity = get_object_or_404(type(self), pk=self.pk)
            prev_file = prev_entity.file
        else:
            prev_file = None

        if self.file != prev_file:
            if not suppressFileDelete:
                # delete the previous file
                self.delete_file(prev_file)
            self.process_file()
        super(S3Mixin, self).save()

    def delete_files(self):
        self.delete_file(self.file)
        self.file = None

    def delete(self, **kwargs):
        self.delete_files()
        super(S3Mixin, self).delete(**kwargs)

    def delete_file(self, file):
        """ Delete S3 object when entity is deleted
        """
        if not file:
            return
        # Delete the AWS prefix of the url
        # e.g: http://9folds.s3.amazonaws.com/agpuaW5lOWZvbGRzchALEglQb3J0Zm9saW8YmAEM/1247867725.01/netanyahou.JPG
        key = file[len(settings.AWS_PREFIX):]
        key = urllib.unquote(key.encode('UTF-8'))
        connection = self.get_aws_connection()
        response = connection.delete(settings.AWS_BUCKET, key)
        logging.info('Trying to delete %s. S3 response code %s ' % (file, response.http_response.status))
        if response.http_response.status != 204:
            msg = 'S3 could not delete object %s' % key
            logging.error(msg)

    def get_file(self):
        file = self.file
        if settings.AWS_CLOUDFRONT and file:
            # Just to ease on crc32, let's trim the file name
            i = zlib.crc32(file[len(settings.AWS_PREFIX):]) % 6 + 1
            file = self.file.replace(settings.AWS_PREFIX, settings.AWS_CLOUDFRONT)
            return file.replace('http://', 'http://m%s.' % i)
        return file

    def get_file_thumb(self):
        url = self.file
        w, h = self.size()
        if (w or h) and url:
            # Just to ease on crc32, let's trim the file name
            i = zlib.crc32(url[len(settings.AWS_PREFIX):]) % 6 + 1
            url = url.replace(settings.AWS_PREFIX, '%s%sx%s/' % (settings.THUMBNAIL_SERVICE, w or 0,h or 0))
            if not settings.ON_PRODUCTION_SERVER:
                url = '%s?domain=%s' % (url, settings.AWS_PREFIX[7:-1])
            return url.replace('http://', 'http://m%s.' % i)
        else:
            return self.get_file()

    def render(self):
        try:
            file = self.get_file()
            params = {'file': file, 'name': self.name}
            return utilmodels.get_render_string_by_extension(file, params, False)
        except Exception,e:
            logging.exception(e)

    def render_visible(self):
        try:
            file = self.get_file()
            if file:
                return utilmodels.get_render_string_by_extension(file, {'file':file, 'name': self.name}, True)
            elif self.file_data:
                return mark_safe(self.file_data)
            else:
                return ''
        except Exception,e:
            logging.exception(e)

    def render_thumb(self):
        try:
            file = self.get_file_thumb()
            if file:
                return utilmodels.get_render_string_by_extension(file, {'file': file, 'name':self.name}, True)
            else:
                return 'No Thumbnail'
        except Exception,e:
            logging.exception(e)

def s3policy(request, prefix, type):
    error_msg = ''
    try:
        s3policy_request.send(sender=request, prefix=prefix)
    except ValueError,e:
        error_msg= e
    acl = 'public-read'
    # TODO: Amazon time difference is strange - investigate
    filename = request.GET['filename']
    extension = os.path.splitext(os.path.basename(filename))[1].lower()
    if extension[1:] not in SUPPORTED_FORMATS.split(','):
        error_msg = 'Filetype %s (%s) is not allowed' % (extension, filename)
    content_type = mimetypes.guess_type(filename)[0]
    if not content_type:
        content_type = 'application/octet-stream'
    big_content_type = content_type.partition('/')[0]
    file_size = int(request.GET.get('file_size', 10))
#        if big_content_type=='image' and file_size>1048576:
#            error_msg = '%s is too large. Max size image 1MB.' % (filename)
#    if file_size>10485760:
#        error_msg = '%s is too large. Max size 10MB.' % (filename)
    # Test for max file size
    if not file_size:
        error_msg = 'File size is zero'
    if file_size > settings.AWS_MAX_FILE_SIZE:
        error_msg = 'Selected file is too large (max is %dMB)' % (settings.AWS_MAX_FILE_SIZE / 1024 / 1024)

    if error_msg:
        logging.info('s3policy error %s' % error_msg)
        return JSONResponse({'errorMessage':error_msg})

    #expires = rfc822.formatdate(time.mktime((datetime.datetime.now() + datetime.timedelta(days=360)).timetuple())),
    key = '%s/%s/%s' % (prefix, time.time(), filename)
    expiration_date = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time()+30000))
    policy_document = simplejson.dumps({"expiration": expiration_date,
                  "conditions": [
                    {"bucket": settings.AWS_BUCKET},
                    {"acl": acl},
                    {"key": key},
                    {"Cache-Control": "public, max-age=2629743"},
                    {"Filename": filename},
                    {"name": filename},
                    {"Content-Type": content_type},
                    ["eq", "$success_action_status", "201"],
                  ]
                })
    policy = base64.b64encode(policy_document.encode('utf-8'))
    signature = base64.b64encode(hmac.new(settings.AWS_SECRET_ACCESS_KEY, policy, sha).digest())

    response = {
        'policy': policy,
        'signature': signature,
        'AWSAccessKeyId': settings.AWS_ACCESS_KEY_ID,
        'Cache-Control': 'public, max-age=2629743',
        'Content-Type': content_type,
        'acl': acl,
        'key': key,
        'success_action_status': '201'
    }

    # Needed when resizing since Flash advancedUpload does not send this and S3 policy fails
    if filename.lower().endswith('jpg') or filename.lower().endswith('png'):
        response['Filename'] = filename

    return JSONResponse(response)

# TODO: some circular imports here...
# Local import
import S3
from django.conf import settings
import utilmodels
import thumb