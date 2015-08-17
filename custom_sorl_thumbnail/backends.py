import os, re
from PIL import ImageEnhance
from PIL import ImageOps
from sorl.thumbnail.base import EXTENSIONS, logger
from django.template.defaultfilters import slugify
from sorl.thumbnail.compat import text_type
from sorl.thumbnail.conf import settings, defaults as default_settings
from sorl.thumbnail import default
from sorl.thumbnail.base import ThumbnailBackend
from sorl.thumbnail.helpers import tokey, serialize
from sorl.thumbnail.images import ImageFile, DummyImageFile


class SEOThumbnailBackend(ThumbnailBackend):
    
    """
    Custom backend for SEO-friendly thumbnail file names/urls.
    based on http://blog.yawd.eu/2012/seo-friendly-image-names-sorl-thumbnail-and-django/
    """
    
    def _get_thumbnail_filename(self, source, geometry_string, options):
        
        """Computes the destination filename"""
        
        split_path = re.sub(r'^%s%s?' % (source.storage.path(''), os.sep), '', source.name).split(os.sep)
        split_path.insert(-1, geometry_string)

        # Make some subdirs to avoid putting too many files in a single dir.
        key = tokey(source.key, geometry_string, serialize(options))
        split_path.insert(-1, key[:2])
        split_path.insert(-1, key[2:4])

        # Attempt to slugify the filename to make it SEO-friendly
        split_name = split_path[-1].split('.')
        try:
            split_path[-1] = '%s.%s' % (slugify('.'.join(split_name[:-1])),
                                        EXTENSIONS[options['format']])
        except:
            # On fail keep the original filename
            pass

        path = os.sep.join(split_path)

        # If the path already starts with THUMBNAIL_PREFIX do not concatenate the PREFIX
        # this way we avoid ending up with a url like /images/images/120x120/my.png
        if not path.startswith(settings.THUMBNAIL_PREFIX):
            return '%s%s' % (settings.THUMBNAIL_PREFIX, path)

        return path


class SafeSEOThumbnailBackend(SEOThumbnailBackend):
    
    def get_thumbnail(self, file_, geometry_string, **options):
        """
        Returns thumbnail as an ImageFile instance for file with geometry and
        options given. First it will try to get it from the key value store,
        secondly it will create it.
        """

        if file_:
            source = ImageFile(file_)
        elif settings.THUMBNAIL_DUMMY:
            return DummyImageFile(geometry_string)
        else:
            return None

        # preserve image filetype
        if settings.THUMBNAIL_PRESERVE_FORMAT:
            options.setdefault('format', self._get_format(source))

        for key, value in self.default_options.items():
            options.setdefault(key, value)
        
        # For the future I think it is better to add options only if they
        # differ from the default settings as below. This will ensure the same
        # filenames being generated for new options at default.
        for key, attr in self.extra_options:
            value = getattr(settings, attr)
            if value != getattr(default_settings, attr):
                options.setdefault(key, value)

        name = self._get_thumbnail_filename(source, geometry_string, options)
        thumbnail = ImageFile(name, default.storage)
        cached = default.kvstore.get(thumbnail)
        if cached and cached.exists():  # Customization
            return cached

        # We have to check exists() because the Storage backend does not
        # overwrite in some implementations.
        if not thumbnail.exists():

            try:
                source_image = default.engine.get_image(source)
            except IOError as e:
                logger.exception(e)
                if settings.THUMBNAIL_DUMMY:
                    return DummyImageFile(geometry_string)
                else:
                    # if S3Storage says file doesn't exist remotely, don't try to
                    # create it and exit early.
                    # Will return working empty image type; 404'd image
                    logger.warn(text_type('Remote file [%s] at [%s] does not exist'),
                                file_, geometry_string)

                    return thumbnail

            # We might as well set the size since we have the image in memory
            image_info = default.engine.get_image_info(source_image)
            options['image_info'] = image_info
            size = default.engine.get_image_size(source_image)

            # Customization
            if options.get('autocrop', None):
                source_image = autocrop(source_image, geometry_string, options)
            # End of customization

            source.set_size(size)
            
            # Customization: race condition, do not raise an OSError when the dir exists.
            # see sorl.thumbnail.images.ImageFile.write, it's not safe to simply throw
            # /sub/dir/name.jpg to django.core.files.storage.FileSystemStorage._save
            full_path = thumbnail.storage.path(name)
            directory = os.path.dirname(full_path)
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except OSError:
                    pass
            # End of customization

            try:
                self._create_thumbnail(source_image, geometry_string, options,
                                       thumbnail)
                self._create_alternative_resolutions(source_image, geometry_string,
                                                     options, thumbnail.name)
            finally:
                default.engine.cleanup(source_image)
                
        options['mtime'] = os.path.getmtime(source.storage.path(source))  # Customization

        # If the thumbnail exists we don't create it, the other option is
        # to delete and write but this could lead to race conditions so I
        # will just leave that out for now.
        default.kvstore.get_or_set(source)
        default.kvstore.set(thumbnail, source)
        return thumbnail


def autocrop(im, requested_size, opts):
    
    if 'autocrop' in opts:
        image = ImageEnhance.Brightness(im).enhance(1.12)
        inverted_image = ImageOps.invert(image)
        bbox = inverted_image.getbbox()
        if bbox:
            im = im.crop(bbox)
        # bw = im.convert("1")
        # bw = bw.filter(ImageFilter.MedianFilter)
        # # white bg
        # bg = Image.new("1", im.size, 255)
        # diff = ImageChops.difference(bw, bg)
        # bbox = diff.getbbox()
        # if bbox:
        #     im = im.crop(bbox)
    return im

