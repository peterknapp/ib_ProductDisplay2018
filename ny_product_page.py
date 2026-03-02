import json, sys
from itertools import islice
from ny_util import http, SlotUpdater, render_short_link_qr_png

class ProductUpdater(SlotUpdater):
    def before_update(self):
        with file("brands/mapping.json", "rb") as f:
            self._brand_mapping = json.load(f)

    def fetch_variant_image_data(self, variant, res='high'):
        image_key = variant['images'][0]['key']
        r = http.get(
            url = "https://%s/csp/images/image/public/%s" % (self._endpoint, image_key),
            params = {
                'res': res,
            },
            timeout = 5,
        )
        r.raise_for_status()
        return r.content

    def generate_slot(self, c, slot_settings):
        print >>sys.stderr, "SLOT", slot_settings

        mode = slot_settings.get('mode', 'random_product')
        if mode == 'random_product':
            # gender = slot_settings.get('gender', 'female')
            brands = slot_settings.get('brands', [])

            params = {
                'country': self._country,
                'limit': 1
            }
            if brands:
                print >>sys.stderr, 'brand filter active: %r' % (brands,)
                params['brand'] = ','.join(brands)

            r = http.get(
                url = "https://%s/csp/products/public/products/randomCollectionProducts" % (self._endpoint,),
                params = params,
                timeout = 5
            )
            r.raise_for_status()
            product = r.json()[0]
            variant = product['variants'][0]
        else:
            product_id = slot_settings.get('product_id', '').strip()
            r = http.get(
                url = "https://%s/csp/products/public/product/%s" % (self._endpoint, product_id),
                params = {
                    'country': self._country
                },
                timeout = 5,
            )
            r.raise_for_status()
            product = r.json()

            variant_id = slot_settings.get('variant_id', '001').strip()
            for variant in product['variants']:
                if variant['id'] == variant_id:
                    print >>sys.stderr, "found the variant"
                    break
        # print >>sys.stderr, "product", pprint.pformat(product)
        # print >>sys.stderr, "variant", pprint.pformat(variant)

        # Fetch Produkt Image
        product_file = c.add_file('product.png',
            self.fetch_variant_image_data(variant)
        )

        # Select Brand Image
        brand_file = c.add_file('brand.png',
            file('brands/' + self._brand_mapping[product['brand']]).read()
        )
        
        # QR Code
        qrcode_file = c.add_file('qrcode.png', render_short_link_qr_png(
            'https://app.newyorker.de/share/product/%s/%s?country=%s' % (
                product['id'], variant['id'], self._country
            )
        ))

        # Pricing
        current_price = False
        if not variant['coming_soon']:
            current_price = variant['current_price']

        original_price = False
        if variant['sale']:
            original_price = variant['original_price']

        # Matching Products
        r = http.get(
            url = "https://%s/csp/products/public/product/matchingProducts" % (self._endpoint,),
            params = {
                'country': self._country,
                'id': product['id'],
                'variantId': variant['id'],
                'limit': 3,
            },
            timeout = 5
        )
        r.raise_for_status()

        matching_products = []
        for idx, matching_product in islice(enumerate(r.json()), 3):
            matching_variant = matching_product['variants'][0]

            matching_price = False
            if not matching_variant['coming_soon']:
                matching_price = matching_variant['current_price']

            matching_products.append(dict(
                img_product = c.add_file('matching-%d.png' % idx,
                    self.fetch_variant_image_data(matching_variant, res='mid')
                ),
                current_price = matching_price,
            ))

        return dict(
            id = product['id'],
            brand = product['brand'],
            web_category = product['web_category'],
            customer_group = product['customer_group'],
            currency = variant['currency'],
            current_price = current_price,
            original_price = original_price,
            img_product = product_file,
            img_brand = brand_file,
            img_qrcode = qrcode_file,
            color = dict(
                r = variant['red'] / 255.,
                g = variant['green'] / 255.,
                b = variant['blue'] / 255.,
            ),
            matching = matching_products,
        )

product_updater = ProductUpdater(
    item_type = 'product',
    refresh_interval = 120,
)

if __name__ == "__main__":
    product_updater.run_forever()
