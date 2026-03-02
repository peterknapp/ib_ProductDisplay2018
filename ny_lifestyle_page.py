from cStringIO import StringIO
from PIL import Image
from ny_util import http, SlotUpdater, render_short_link_qr_png
from itertools import count

image_id = count().next

class LifeStyleUpdater(SlotUpdater):
    def generate_slot(self, c, slot_settings):
        r = http.post(
            url = "https://%s/api/functions/loadTimeline" % (self._endpoint,),
            data = {
                'countryCode': self._country.upper(),
            },
            headers = {
                'X-Parse-Application-Id': 'newYorkerApi',
            },
            timeout = 5,
        )
        r.raise_for_status()
        posts = r.json()['result']

        def fetch_post(post):
            r = http.get(
                url = post['image']['url'],
                timeout = 5,
            )
            r.raise_for_status()

            # Make sure it's readable by info-beamer
            im = Image.open(StringIO(r.content))
            width, height = im.size
            if width > 2048 or height > 2048:
                im.thumbnail((2048, 2048), Image.ANTIALIAS)
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            jpeg = StringIO()
            im.save(jpeg, 'JPEG')
            image_file = c.add_file('image-%d.jpg' % image_id(), jpeg.getvalue())

            qrcode_file = c.add_file('qrcode-%d.png' % image_id(), render_short_link_qr_png(
                'https://app.newyorker.de/cmd?action=START_LIFESTYLE&lifestyleId=%s' % post['id']
            ))

            return dict(
                img_background = image_file,
                img_qrcode = qrcode_file,

                # See issue #8 for this mapping
                category = post['header'].upper().strip(),
                headline = post['description'].upper().strip(),
                text = post['message'].strip(),
            )

        selected_posts = []
        for post in posts:
            if post['source'] == 'LIFESTYLE':
                selected_posts.append(fetch_post(post))
            if len(selected_posts) == 2:
                break

        if not selected_posts:
            raise ValueError("no lifestyle found")

        return selected_posts

lifestyle_updater = LifeStyleUpdater(
    item_type = 'lifestyle',
    refresh_interval = 120,
)

if __name__ == "__main__":
    lifestyle_updater.run_forever()
