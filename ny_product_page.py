import json, os, sys
from itertools import islice
from ny_util import http, SlotUpdater, render_short_link_qr_png

class ProductUpdater(SlotUpdater):
    def before_update(self):
        with file("brands/mapping.json", "rb") as f:
            self._brand_mapping = json.load(f)

    def _file_bytes(self, path):
        with file(path, "rb") as f:
            return f.read()

    def _unwrap_product_payload(self, payload):
        if isinstance(payload, list):
            if not payload:
                raise ValueError("empty product list payload")
            if not isinstance(payload[0], dict):
                raise ValueError("unexpected list payload shape")
            return payload[0]

        if not isinstance(payload, dict):
            raise ValueError("unexpected payload type %r" % (type(payload),))

        result = payload.get("result")
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]

        data = payload.get("data")
        if isinstance(data, dict):
            if isinstance(data.get("product"), dict):
                return data["product"]
            if data.get("variants"):
                return data

        return payload

    def _variants_from_product(self, product):
        variants = []
        if isinstance(product, dict):
            raw = product.get("variants")
            if isinstance(raw, list):
                variants = raw

            if not variants:
                data = product.get("data")
                if isinstance(data, dict):
                    raw = data.get("variants")
                    if isinstance(raw, list):
                        variants = raw
        return [variant for variant in variants if isinstance(variant, dict)]

    def _extract_products_from_payload(self, payload):
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]

        if not isinstance(payload, dict):
            return []

        products = []
        for key in ("result", "products", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                products.extend([p for p in value if isinstance(p, dict)])

        data = payload.get("data")
        if isinstance(data, list):
            products.extend([p for p in data if isinstance(p, dict)])
        elif isinstance(data, dict):
            for key in ("result", "products", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    products.extend([p for p in value if isinstance(p, dict)])
            if isinstance(data.get("product"), dict):
                products.append(data["product"])

        # If this payload itself already looks like a product, accept it.
        if payload.get("variants") or payload.get("brand") or payload.get("id"):
            products.append(payload)

        return products

    def _select_variant(self, product, requested_variant):
        variants = self._variants_from_product(product)
        if not variants:
            raise ValueError("product has no variants")

        requested_variant = (requested_variant or "").strip()
        if requested_variant:
            for variant in variants:
                if str(variant.get("id", "")).strip() == requested_variant:
                    print >>sys.stderr, "found requested variant %s" % requested_variant
                    return variant

        return variants[0]

    def _extract_image_ref(self, variant):
        images = variant.get("images")
        if not isinstance(images, list):
            raise ValueError("variant images missing")

        for image in images:
            if not isinstance(image, dict):
                continue

            for key_name in ("key", "image_key", "id", "hash", "token"):
                key = image.get(key_name)
                if isinstance(key, basestring) and key.strip():
                    return key.strip()

            for key_name in ("url", "image_url", "src", "href"):
                url = image.get(key_name)
                if isinstance(url, basestring) and url.strip():
                    return url.strip()

        raise ValueError("no usable image reference in variant")

    def _read_brand_image(self, brand):
        mapped_file = self._brand_mapping.get(brand, "")
        if mapped_file:
            mapped_path = os.path.join("brands", mapped_file)
            if os.path.exists(mapped_path):
                return self._file_bytes(mapped_path)

        for fallback in ("package.png", "empty.png"):
            if os.path.exists(fallback):
                return self._file_bytes(fallback)

        return ""

    def _safe_color_channel(self, value):
        try:
            value = float(value)
        except:
            return 0.0
        if value > 1.0:
            value = value / 255.0
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value

    def _normalize_mode(self, mode):
        mode = (mode or "").strip().lower()
        if mode in ("single_product", "single", "one", "product"):
            return "single_product"
        if mode in ("random", "random_product", "rand"):
            return "random_product"
        return "random_product"

    def _fetch_random_product(self, brands):
        if isinstance(brands, basestring):
            brands = [brands] if brands.strip() else []
        if not isinstance(brands, list):
            brands = []

        params = {
            'country': self._country,
            'limit': 1,
        }
        if brands:
            print >>sys.stderr, 'brand filter active: %r' % (brands,)
            params['brand'] = ','.join(brands)

        endpoints = [
            "https://%s/csp/products/public/products/randomCollectionProducts" % (self._endpoint,),
            "https://%s/csp/products/public/product/randomCollectionProducts" % (self._endpoint,),
            "https://%s/csp/products/public/products/randomProducts" % (self._endpoint,),
            "https://%s/csp/products/public/product/randomProducts" % (self._endpoint,),
            "https://%s/csp/products/public/products/random" % (self._endpoint,),
            "https://%s/csp/products/public/product/random" % (self._endpoint,),
        ]

        errors = []
        for url in endpoints:
            try:
                r = http.get(
                    url = url,
                    params = params,
                    timeout = 5
                )
                r.raise_for_status()
                products = self._extract_products_from_payload(r.json())
                if not products:
                    errors.append("empty product list from %s" % (url,))
                    continue
                return products[0]
            except Exception as err:
                errors.append("%s: %r" % (url, err))

        raise ValueError("random product fetch failed: %s" % (" | ".join(errors),))

    def fetch_variant_image_data(self, variant, res='high'):
        image_ref = self._extract_image_ref(variant)
        if image_ref.startswith("http://") or image_ref.startswith("https://"):
            r = http.get(
                url = image_ref,
                timeout = 5,
            )
            r.raise_for_status()
            return r.content

        last_error = None
        for params in ({'res': res}, {}):
            try:
                r = http.get(
                    url = "https://%s/csp/images/image/public/%s" % (self._endpoint, image_ref),
                    params = params,
                    timeout = 5,
                )
                r.raise_for_status()
                return r.content
            except Exception as err:
                last_error = err

        raise last_error

    def generate_slot(self, c, slot_settings):
        print >>sys.stderr, "SLOT", slot_settings

        mode = self._normalize_mode(slot_settings.get('mode', 'random_product'))
        if mode == 'random_product':
            brands = slot_settings.get('brands', [])
            try:
                product = self._fetch_random_product(brands)
                variant = self._select_variant(product, "")
            except Exception as err:
                print >>sys.stderr, "random mode failed: %r" % (err,)
                fallback_product_id = slot_settings.get('product_id', '').strip()
                if fallback_product_id:
                    try:
                        r = http.get(
                            url = "https://%s/csp/products/public/product/%s" % (self._endpoint, fallback_product_id),
                            params = {
                                'country': self._country
                            },
                            timeout = 5,
                        )
                        r.raise_for_status()
                        product = self._unwrap_product_payload(r.json())
                        variant = self._select_variant(product, slot_settings.get('variant_id', '').strip())
                    except Exception as err2:
                        print >>sys.stderr, "random fallback(single product) failed: %r" % (err2,)
                        product = {'id': 'unknown', 'brand': '', 'variants': [{}]}
                        variant = {}
                else:
                    product = {'id': 'unknown', 'brand': '', 'variants': [{}]}
                    variant = {}
        else:
            product_id = slot_settings.get('product_id', '').strip()
            if not product_id:
                print >>sys.stderr, "single_product mode without product_id"
                product = {'id': 'unknown', 'brand': '', 'variants': [{}]}
                variant = {}
            else:
                try:
                    r = http.get(
                        url = "https://%s/csp/products/public/product/%s" % (self._endpoint, product_id),
                        params = {
                            'country': self._country
                        },
                        timeout = 5,
                    )
                    r.raise_for_status()
                    product = self._unwrap_product_payload(r.json())

                    variant_id = slot_settings.get('variant_id', '').strip()
                    variant = self._select_variant(product, variant_id)
                except Exception as err:
                    print >>sys.stderr, "single_product fetch failed: %r" % (err,)
                    product = {'id': product_id or 'unknown', 'brand': '', 'variants': [{}]}
                    variant = {}
        # print >>sys.stderr, "product", pprint.pformat(product)
        # print >>sys.stderr, "variant", pprint.pformat(variant)

        product_id = product.get('id') or variant.get('product_id') or "unknown"
        brand = product.get('brand') or ""
        web_category = product.get('web_category') or product.get('maintenance_group') or "Produkt"
        customer_group = product.get('customer_group') or "FEMALE"
        currency = variant.get('currency') or "EUR"
        variant_id = variant.get('id') or ""

        # Fetch Produkt Image
        try:
            product_file = c.add_file('product.png',
                self.fetch_variant_image_data(variant)
            )
        except Exception as err:
            print >>sys.stderr, "failed to fetch product image: %r" % (err,)
            product_file = c.add_file('product.png', self._file_bytes('package.png'))

        # Select Brand Image
        brand_file = c.add_file('brand.png',
            self._read_brand_image(brand)
        )
        
        # QR Code
        try:
            qrcode_data = render_short_link_qr_png(
                'https://app.newyorker.de/share/product/%s/%s?country=%s' % (
                    product_id, variant_id, self._country
                )
            )
        except Exception as err:
            print >>sys.stderr, "failed to create qrcode: %r" % (err,)
            qrcode_data = self._file_bytes('empty.png')
        qrcode_file = c.add_file('qrcode.png', qrcode_data)

        # Pricing
        current_price = False
        if not variant.get('coming_soon', False):
            current_price = variant.get('current_price', False)

        original_price = False
        if variant.get('sale', False):
            original_price = variant.get('original_price', False)

        # Matching Products
        matching_products = []
        try:
            r = http.get(
                url = "https://%s/csp/products/public/product/matchingProducts" % (self._endpoint,),
                params = {
                    'country': self._country,
                    'id': product_id,
                    'variantId': variant_id,
                    'limit': 3,
                },
                timeout = 5
            )
            r.raise_for_status()

            matching_payload = r.json()
            if isinstance(matching_payload, dict):
                matching_payload = matching_payload.get('result', [])
            if not isinstance(matching_payload, list):
                matching_payload = []

            for idx, matching_product in islice(enumerate(matching_payload), 3):
                if not isinstance(matching_product, dict):
                    continue
                try:
                    matching_variant = self._select_variant(matching_product, "")
                except Exception as err:
                    print >>sys.stderr, "skip matching product without variant: %r" % (err,)
                    continue

                matching_price = False
                if not matching_variant.get('coming_soon', False):
                    matching_price = matching_variant.get('current_price', False)

                try:
                    matching_file_data = self.fetch_variant_image_data(matching_variant, res='mid')
                except Exception as err:
                    print >>sys.stderr, "failed to fetch matching image: %r" % (err,)
                    matching_file_data = self._file_bytes('empty.png')

                matching_products.append(dict(
                    img_product = c.add_file('matching-%d.png' % idx, matching_file_data),
                    current_price = matching_price,
                ))
        except Exception as err:
            print >>sys.stderr, "matching products unavailable: %r" % (err,)

        return dict(
            id = product_id,
            brand = brand,
            web_category = web_category,
            customer_group = customer_group,
            currency = currency,
            current_price = current_price,
            original_price = original_price,
            img_product = product_file,
            img_brand = brand_file,
            img_qrcode = qrcode_file,
            color = dict(
                r = self._safe_color_channel(variant.get('red', 0)),
                g = self._safe_color_channel(variant.get('green', 0)),
                b = self._safe_color_channel(variant.get('blue', 0)),
            ),
            matching = matching_products,
        )

product_updater = ProductUpdater(
    item_type = 'product',
    refresh_interval = 120,
)

if __name__ == "__main__":
    product_updater.run_forever()
