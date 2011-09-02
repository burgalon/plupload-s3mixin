var onPluploadFilesAdded = function(up, files) {
    $('.upload-error').remove();
    // Add to queue list
    $.each(files, function(i, file) {
        up.settings.filelistelement.append(
                '<div id="' + file.id + '">' +
                        file.name + ' (' + plupload.formatSize(file.size) + ') <b>Thinking...</b>' +
                        '</div>');
        if (file.size > up.settings.max_file_size) {
            var msg = file.name + ' size ' + plupload.formatSize(file.size) + ' is more than the limit (' + plupload.formatSize(up.settings.max_file_size) + ')';
            onPluploadError(up, {code: 403, message: msg, file: {name: file.name}});
            $('#' + file.id).remove();
            up.removeFile(file);
        }
    });
    if(up.settings.auto_upload) up.start();
    else
    {
        up.settings.form.submit(function(){up.start(); return false; });
    }
};

var onPluploadUploadFile = function(up, file) {
    // Get Policy Signature for next file
    var ret = true;
    $.ajax({
        url: this.settings.signature_url,
        dataType: 'json',
        async: false,
        data: {'file_size': file.size, filename: file.name},
        success: function(data) {
            if(data.errorMessage)
            {
                onPluploadError(up, {code: 403, message: data.errorMessage, file: {name: file.name}});
                ret =  false;
                $('#' + file.id).remove();
                up.removeFile(file);
                up.stop();
                up.start();
                return;
            }
            up.settings.multipart_params = data;
        },
        error: function(jqXHR, textStatus, errorThrown) {
                onPluploadError(up, {code: textStatus, message: errorThrown, file: {name: file.name}});
                ret = false;
                $('#' + file.id).remove();
                up.removeFile(file);
                up.stop();
                up.start();
        }
    });
    return ret;
};

var onPluploadUploadProgress = function(up, file) {
    $('#' + file.id + " b").html(file.percent + "%");
};

var onPluploadFileUploaded = function(up, file, response) {
    $('#' + file.id).remove();
    var file_url = up.settings.url + encodeURI(up.settings.multipart_params.key);
    var form = up.settings.form;
    form.find('input[name='+up.settings.file_input_name+']').val(file_url);
};

var onPluploadError = function(up, err) {
    up.settings.filelistelement.append("<div class='upload-error'>" + err.message +
            " <i>(" + err.code + ")</i>" +
            "</div>"
            );
};
