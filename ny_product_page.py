import json, os, sys, time
from itertools import islice
from ny_util import http, SlotUpdater, render_short_link_qr_png

class ProductUpdater(SlotUpdater):
    def before_update(self):
        with file("brands/mapping.json", "rb") as f:
            self._brand_mapping = json.load(f)
        if not hasattr(self, "_last_random_product_by_slot"):
            self._last_random_product_by_slot = {}
        if not hasattr(self, "_rotation_index_by_slot"):
            self._rotation_index_by_slot = {}

        # Match update cadence to product playlist duration(s).
        try:
            with file("config.json", "rb") as f:
                config = json.load(f)
            product_durations = []
            for item in config.get("playlist", []):
                if item.get("type") != "product":
                    continue
                try:
                    duration = float(item.get("duration", 10))
                except Exception:
                    duration = 10.0
                if duration > 0:
                    product_durations.append(duration)

            if product_durations:
                # For multiple product slots we update at least as frequently
                # as the shortest configured product duration.
                self._refresh_interval = max(1, min(product_durations))
            else:
                self._refresh_interval = 10
        except Exception as err:
            print >>sys.stderr, "failed to derive product refresh from playlist durations: %r" % (err,)
            self._refresh_interval = 10

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
            products = []
            for item in payload:
                if isinstance(item, dict):
                    products.append(item)
                elif isinstance(item, basestring) and item.strip():
                    products.append({'id': item.strip()})
            return products

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

    def _extract_product_id(self, product):
        if not isinstance(product, dict):
            return ""

        for key in ("id", "product_id", "productId"):
            value = product.get(key)
            if isinstance(value, basestring) and value.strip():
                return value.strip()

        nested = product.get("product")
        if isinstance(nested, dict):
            for key in ("id", "product_id", "productId"):
                value = nested.get(key)
                if isinstance(value, basestring) and value.strip():
                    return value.strip()

        return ""

    def _extract_product_title(self, product):
        if not isinstance(product, dict):
            return ""

        for key in ("product_name", "name", "title", "label"):
            value = product.get(key)
            if isinstance(value, basestring) and value.strip():
                return value.strip()

        descriptions = product.get("descriptions")
        if isinstance(descriptions, list):
            preferred = (self._language or "de").strip().upper()
            for lang in (preferred, "DE", "EN"):
                for entry in descriptions:
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("language", "")).strip().upper() != lang:
                        continue
                    text = entry.get("description")
                    if isinstance(text, basestring) and text.strip():
                        return text.strip()

            for entry in descriptions:
                if not isinstance(entry, dict):
                    continue
                text = entry.get("description")
                if isinstance(text, basestring) and text.strip():
                    return text.strip()

        return ""

    def _pick_rotating_product(self, products, slot_key):
        if not products:
            raise ValueError("cannot pick from empty product list")
        if len(products) == 1:
            chosen = products[0]
            chosen_id = self._extract_product_id(chosen)
            if chosen_id:
                self._last_random_product_by_slot[slot_key] = chosen_id
            return chosen

        def sort_key(product):
            product_id = self._extract_product_id(product)
            if product_id:
                return product_id
            return json.dumps(product, sort_keys=True)

        products = sorted(products, key=sort_key)
        idx = self._rotation_index_by_slot.get(slot_key, -1) + 1
        idx = idx % len(products)
        self._rotation_index_by_slot[slot_key] = idx
        chosen = products[idx]
        chosen_id = self._extract_product_id(chosen)
        if chosen_id:
            self._last_random_product_by_slot[slot_key] = chosen_id
        return chosen

    def _extract_random_product_ids(self, payload):
        ids = []
        seen = set()

        def add(candidate):
            if not isinstance(candidate, basestring):
                return
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            ids.append(candidate)

        def walk(value, parent_key=""):
            if isinstance(value, dict):
                for key, sub in value.items():
                    normalized = str(key).strip().lower()
                    if normalized in ("id", "product_id", "productid"):
                        add(sub)
                    walk(sub, normalized)
            elif isinstance(value, list):
                for item in value:
                    walk(item, parent_key)
            elif isinstance(value, basestring):
                # Accept plain string lists of product ids if we are under a likely id key.
                if parent_key in ("ids", "product_ids", "productids"):
                    add(value)

        walk(payload)
        return ids

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

        def score(variant):
            score = 0
            images = variant.get("images")
            if isinstance(images, list) and len(images) > 0:
                score += 2
            if not variant.get("coming_soon", False):
                score += 2
            if variant.get("current_price") is not None:
                score += 1
            return score

        variants = sorted(variants, key=score, reverse=True)
        return variants[0]

    def _extract_image_ref(self, variant):
        images = variant.get("images")
        if not isinstance(images, list):
            raise ValueError("variant images missing")

        def image_ref(image):
            for key_name in ("key", "image_key", "id", "hash", "token"):
                key = image.get(key_name)
                if isinstance(key, basestring) and key.strip():
                    return key.strip()
            for key_name in ("url", "image_url", "src", "href"):
                url = image.get(key_name)
                if isinstance(url, basestring) and url.strip():
                    return url.strip()
            return None

        def norm(value):
            if isinstance(value, basestring):
                return value.strip().upper()
            return ""

        scored = []
        for image in images:
            if not isinstance(image, dict):
                continue
            ref = image_ref(image)
            if not ref:
                continue

            img_type = norm(image.get("type"))
            img_angle = norm(image.get("angle"))
            has_thumb = bool(image.get("has_thumbnail", False))

            score = 0
            if has_thumb:
                score += 1
            if img_angle == "FRONT":
                score += 2
            if img_type in ("CUTOUT", "MODEL", "PACKSHOT"):
                score += 2
            if "LOGO" in img_type or "LOGO" in ref.upper():
                score -= 5

            scored.append((score, ref))

        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]

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

    def _fetch_random_product(self, brands, slot_settings, slot_key):
        if isinstance(brands, basestring):
            brands = [brands] if brands.strip() else []
        if not isinstance(brands, list):
            brands = []

        base_params = {
            'country': self._country,
            # Ask for multiple candidates so we can choose a displayable one.
            'limit': 10,
        }
        gender = (slot_settings.get('gender', 'female') or 'female').strip().lower()
        customer_group = "MALE" if gender == "male" else "FEMALE"

        endpoints = [
            "https://%s/csp/products/public/products/randomCollectionProducts" % (self._endpoint,),
            "https://%s/csp/products/public/product/randomCollectionProducts" % (self._endpoint,),
            "https://%s/csp/products/public/products/randomProducts" % (self._endpoint,),
            "https://%s/csp/products/public/product/randomProducts" % (self._endpoint,),
            "https://%s/csp/products/public/products/random" % (self._endpoint,),
            "https://%s/csp/products/public/product/random" % (self._endpoint,),
        ]

        errors = []
        param_variants = []

        # Broad compatibility for backend variants.
        enriched = dict(base_params)
        enriched['gender'] = gender
        enriched['customerGroup'] = customer_group
        enriched['customer_group'] = customer_group
        enriched['language'] = (self._language or 'de')
        param_variants.append(enriched)

        enriched_short = dict(base_params)
        enriched_short['gender'] = gender
        enriched_short['language'] = (self._language or 'de')
        param_variants.append(enriched_short)

        if brands:
            print >>sys.stderr, 'brand filter active: %r' % (brands,)
            with_brand = dict(base_params)
            with_brand['brand'] = ','.join(brands)
            param_variants.append(with_brand)

            with_brand_enriched = dict(enriched)
            with_brand_enriched['brand'] = ','.join(brands)
            param_variants.insert(0, with_brand_enriched)
        param_variants.append(base_params)

        for url in endpoints:
            for params in param_variants:
                for method in ("get", "post"):
                    try:
                        if method == "get":
                            r = http.get(
                                url = url,
                                params = params,
                                timeout = 5
                            )
                        else:
                            r = http.post(
                                url = url,
                                data = params,
                                timeout = 5
                            )
                        r.raise_for_status()
                        payload = r.json()
                        products = self._extract_products_from_payload(payload)
                        if not products:
                            product_ids = self._extract_random_product_ids(payload)
                            if product_ids:
                                return {'id': product_ids[0]}
                            errors.append("empty product list from %s %s params=%r" % (url, method, params))
                            continue

                        # Prefer products with non-coming-soon variants and usable images.
                        scored = []
                        for product in products:
                            product_id = self._extract_product_id(product)
                            try:
                                variant = self._select_variant(product, "")
                            except Exception:
                                # Product without embedded variants might still be usable after
                                # we enrich it with product/<id> in generate_slot.
                                if product_id:
                                    scored.append((1, product))
                                continue

                            images = variant.get("images")
                            has_images = isinstance(images, list) and len(images) > 0
                            coming_soon = bool(variant.get("coming_soon", False))

                            score = 0
                            if has_images:
                                score += 2
                            if not coming_soon:
                                score += 1
                            if product_id:
                                score += 1
                            scored.append((score, product))

                        if scored:
                            scored.sort(key=lambda item: item[0], reverse=True)
                            top_score = scored[0][0]
                            top_products = [product for score, product in scored if score == top_score]
                            return self._pick_rotating_product(top_products, slot_key)

                        return self._pick_rotating_product(products, slot_key)
                    except Exception as err:
                        errors.append("%s %s params=%r: %r" % (url, method, params, err))

        raise ValueError("random product fetch failed: %s" % (" | ".join(errors),))

    def _fetch_product_by_id(self, product_id):
        product_id = (product_id or "").strip()
        if not product_id:
            raise ValueError("empty product_id")

        r = http.get(
            url = "https://%s/csp/products/public/product/%s" % (self._endpoint, product_id),
            params = {
                'country': self._country
            },
            timeout = 5,
        )
        r.raise_for_status()
        return self._unwrap_product_payload(r.json())

    def _fetch_matching_products(self, product_id, variant_id, limit=10):
        product_id = (product_id or "").strip()
        variant_id = (variant_id or "").strip()
        if not product_id:
            return []

        params = {
            'country': self._country,
            'id': product_id,
            'limit': int(limit),
        }
        if variant_id:
            params['variantId'] = variant_id

        r = http.get(
            url = "https://%s/csp/products/public/product/matchingProducts" % (self._endpoint,),
            params = params,
            timeout = 5,
        )
        r.raise_for_status()

        payload = r.json()
        if isinstance(payload, dict):
            payload = payload.get('result', [])
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

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
        for params in (
            {'res': 'full-hd', 'frame': '2_3'},
            {'res': 'full-hd'},
            {'res': res},
            {'frame': '2_3'},
            {},
        ):
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
        slot_key = slot_settings.get('_slot_uuid', 'default-random-slot')

        mode = self._normalize_mode(slot_settings.get('mode', 'random_product'))
        if mode == 'random_product':
            brands = slot_settings.get('brands', [])
            try:
                random_product = self._fetch_random_product(brands, slot_settings, slot_key)
                random_product_id = self._extract_product_id(random_product)
                if random_product_id:
                    try:
                        product = self._fetch_product_by_id(random_product_id)
                    except Exception as err:
                        print >>sys.stderr, "failed to enrich random product %s: %r" % (random_product_id, err)
                        product = random_product
                else:
                    product = random_product
                variant = self._select_variant(product, "")
            except Exception as err:
                print >>sys.stderr, "random mode failed: %r" % (err,)
                # Fallback randomization strategy when backend random endpoints are broken:
                # use matching products from a configured seed product_id.
                seed_product_id = slot_settings.get('product_id', '').strip()
                seed_variant_id = slot_settings.get('variant_id', '').strip()
                if seed_product_id:
                    try:
                        seed_product = self._fetch_product_by_id(seed_product_id)
                        seed_variant = self._select_variant(seed_product, seed_variant_id)
                        matching = self._fetch_matching_products(
                            seed_product.get('id') or seed_product_id,
                            seed_variant.get('id') or seed_variant_id,
                            limit = 20,
                        )
                        if matching:
                            product = self._pick_rotating_product(matching, slot_key)
                            # Enrich to stable full payload when possible.
                            product_id = self._extract_product_id(product)
                            if product_id:
                                try:
                                    product = self._fetch_product_by_id(product_id)
                                except Exception as err2:
                                    print >>sys.stderr, "matching enrich failed for %s: %r" % (product_id, err2)
                            variant = self._select_variant(product, "")
                        else:
                            print >>sys.stderr, "random fallback: no matching products, use seed product"
                            product = seed_product
                            variant = seed_variant
                    except Exception as err2:
                        print >>sys.stderr, "random fallback from seed failed: %r" % (err2,)
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
                    product = self._fetch_product_by_id(product_id)
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
        print >>sys.stderr, "resolved product slot mode=%s product_id=%s variant_id=%s" % (
            mode, product_id, variant_id
        )

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
            variant_id = variant_id,
            product_title = self._extract_product_title(product),
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
            debug_mode = mode,
            debug_slot = slot_key,
            debug_updated_at = int(time.time()),
        )

product_updater = ProductUpdater(
    item_type = 'product',
    refresh_interval = 30,
)

if __name__ == "__main__":
    product_updater.run_forever()
