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
    up.start();
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
            }
            up.settings.multipart_params = data;
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
    // Post form and replaces the updated catalog/element
    $.post(
            form.attr('action'), // url
            form.serialize(), // data
            function(response) { // success
                var catalogs = $('.catalog');
                $(response).find('.catalog').each(function(i){
                     $(catalogs[i]).replaceWith(this);
                });
                // Replace file link the Page Form
                $(response).find('#id_page-file_preview').each(function(i){
                     $('#id_page-file_preview').replaceWith(this);
                });
                // Update hidden page-files and page-pages
                $('#page-form input[type=hidden]').remove();
                $(response).find('#page-form input[type=hidden]').appendTo('#page-form');

                // Rehook sortables
                if(typeof sub_page_sortable != 'undefined') sub_page_sortable();
                if(typeof files_sortable != 'undefined') files_sortable();
            }
    );
};

var onPluploadError = function(up, err) {
    up.settings.filelistelement.append("<div class='upload-error'>" + err.message +
            " <i>(" + err.code + ")</i>" +
            "</div>"
            );
};
