import os
import time
from django.conf import settings
from django.core.urlresolvers import reverse
from django import forms
from django.utils.safestring import mark_safe
from mediagenerator.utils import media_url
from s3mixin.models import SUPPORTED_FORMATS

class S3FileWidget(forms.HiddenInput):
    is_hidden = False

    class Meta:
        abstract = True

    def __init__(self, auto_upload=False, required=True, allowed_types=SUPPORTED_FORMATS, multi_selection=True, signature_url='../s3policy', *args, **kwargs):
        self.auto_upload = auto_upload
        self.required = required
        self.allowed_types = allowed_types
        self.signature_url = signature_url
        self.multi_selection = multi_selection
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
            <span id="%(id)s-upload" class="button-gd">Select File</span></p>
            <p id="%(id)s-filelist"></p>''' %
            {'id': self.attrs['id']})

    def javascript(self):
        return mark_safe(u'''
                var uploader =  new plupload.Uploader({
                    runtimes : 'flash',
                    use_query_string: false,
                    multipart: true,
                    url: '%(aws_prefix)s',
                    multi_selection: %(multi_selection)s,
                    form: $('#%(id)s').closest('form'),
                    signature_url: '%(signature_url)s',
                    auto_upload: '%(auto_upload)s',
                    browse_button : '%(id)s-upload',
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
                    'multi_selection': 'true' if self.multi_selection else 'false',
                    'signature_url': self.signature_url,
                   # swf: '%ss3_upload.swf',
                    'swf_url': media_url('plupload/plupload.flash.swf'),
                   # $('#%s').val('');
                    'id': self.attrs['id'],
                    # /* auto_upload */
                    'auto_upload': 'true' if self.auto_upload else 'false',
                   # document.getElementById('%s').value='%s' + '%s' + filename;
                    'aws_prefix': settings.AWS_PREFIX,
                   # document.getElementById('%s').value='%s' + '%s' + filename;
                    'name': self.name,
                    'allowed_types': self.allowed_types,
                    'max_file_size': settings.AWS_MAX_FILE_SIZE,
                   } )