import os.path
import logging
import re
from django.template import Library
from sorl.thumbnail.conf import settings
from sorl.thumbnail.images import DummyImageFile
from sorl.thumbnail import default
from sorl.thumbnail.templatetags.thumbnail import ThumbnailNode
from sorl.thumbnail.base import ThumbnailBackend
from sorl.thumbnail.images import ImageFile
from sorl.thumbnail import default
from custom_sorl_thumbnail.backends import SafeSEOThumbnailBackend

register = Library()
kw_pat = re.compile(r'^(?P<key>[\w]+)=(?P<value>.+)$')
logger = logging.getLogger('sorl.thumbnail')

custom_backend = SafeSEOThumbnailBackend()

#@register.tag('thumbnail')
class SafeThumbnailNode(ThumbnailNode):
    '''
    This template tag ignores settings.THUMBNAIL_BACKEND
    It always uses the SafeSEOThumbnailBackend. 
    '''

    def _render(self, context):
        file_ = self.file_.resolve(context)
        geometry = self.geometry.resolve(context)
        options = {}
        for key, expr in self.options:
            noresolve = {u'True': True, u'False': False, u'None': None}
            value = noresolve.get(str(expr), expr.resolve(context))
            if key == 'options':
                options.update(value)
            else:
                options[key] = value

        thumbnail = None
        if file_:
            thumbnail = custom_backend.get_thumbnail(###customization
                file_, geometry, **options
                )
        elif settings.THUMBNAIL_DUMMY:
            thumbnail = DummyImageFile(geometry)

        if not thumbnail or (isinstance(thumbnail, DummyImageFile) and self.nodelist_empty):
            if self.nodelist_empty:
                return self.nodelist_empty.render(context)
            else:
                return ''

        if self.as_var:
            context.push()
            context[self.as_var] = thumbnail
            output = self.nodelist_file.render(context)
            context.pop()
        else:
            output = thumbnail.url

        return output


@register.tag
def thumbnail(parser, token):
    return SafeThumbnailNode(parser, token)
