import sys
from cStringIO import StringIO
from PIL import Image
from ny_util import http, SlotUpdater, UrlCache
from itertools import count

image_id = count().next

CoverCache = UrlCache('dressfm', max_cached=64)

class DressFMUpdater(SlotUpdater):
    def generate_slot(self, c, slot_settings):
        stream = slot_settings.get('stream', 'nyir-ger')
        r = http.get(
            url = "https://streamwatch.newyorker.de/api/stream/%s/current" % stream,
            timeout = 5,
        )
        r.raise_for_status()
        song = r.json()
        print >>sys.stderr, song

        cover = CoverCache.fetch(
            url = song['coverUrl'],
            timeout = 5,
        )

        # Make sure it's readable by info-beamer
        im = Image.open(StringIO(cover))
        width, height = im.size
        if width > 2048 or height > 2048:
            im.thumbnail((2048, 2048), Image.ANTIALIAS)
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        jpeg = StringIO()
        im.save(jpeg, 'JPEG')
        cover_file = c.add_file('covert-%d.jpg' % image_id(), jpeg.getvalue())

        return dict(
            img_cover = cover_file,
            artist = song['artist'],
            title = song['title'],
        )

dressfm_updater = DressFMUpdater(
    item_type = 'dressfm',
    refresh_interval = 10,
)

if __name__ == "__main__":
    dressfm_updater.run_forever()
