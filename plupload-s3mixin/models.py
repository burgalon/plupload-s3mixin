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

import S3
import utils

SUPPORTED_FORMATS = 'jpg,png,gif,css,html,js,pdf,swf,ico,mp3'

class S3Mixin(models.Model):
    """A mixin class that gives thumbnail services for files uploaded to Amazon S3
    Also on delete it will delete the object from S3
    """
    file = models.URLField(null=True, blank=True, verify_exists=False, max_length=1000)
#    file = models.CharField(null=True, max_length=300)
    file_data = models.TextField(null=True, editable=False)

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
        if self.pk and not suppressFileDelete:
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
            return utils.get_render_string_by_extension(file, params, False)
        except Exception,e:
            logging.exception(e)

    def render_visible(self):
        try:
            file = self.get_file()
            if file:
                return utils.get_render_string_by_extension(file, {'file':file, 'name': self.name}, True)
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
                return utils.get_render_string_by_extension(file, {'file': file, 'name':self.name}, True)
            else:
                return 'No Thumbnail'
        except Exception,e:
            logging.exception(e)