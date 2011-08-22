import base64
import time
import logging
import mimetypes
import os
from django.utils import simplejson
from djangotoolbox.http import JSONResponse
from s3mixin.models import SUPPORTED_FORMATS
from django.conf import settings
import hmac, sha

def s3policy(request, prefix):
    error_msg = ''
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