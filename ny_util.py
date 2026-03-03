import os, sys, json, time, requests, hashlib
sys.path.insert(0, 'qrcode.zip')
import qrcode
from cStringIO import StringIO
from datasync import DistributedDataClient

SERIAL = os.environ['SERIAL']
TESTMODE = os.getenv('TESTMODE') == 'yes'

def init_http_session(retries=3):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'digital signs (device %s)' % SERIAL
    })
    return session

http = init_http_session()

if TESTMODE:
    import httplib, logging
    httplib.HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    req_log = logging.getLogger('requests.packages.urllib3')
    req_log.setLevel(logging.DEBUG)
    req_log.propagate = True

class UrlCache(object):
    def __init__(self, prefix, max_cached=64):
        self._prefix = prefix
        self._max_cached = max_cached
        self._fifo = []

    def url_to_cache_name(self, url):
        return 'cache-%s-%s' % (self._prefix, hashlib.md5(url).hexdigest())

    def fetch(self, url, **kwargs):
        filename = self.url_to_cache_name(url)
        try:
            with file(filename, 'rb') as f:
                return f.read()
        except:
            pass
        r = http.get(url, **kwargs)
        r.raise_for_status()
        content = r.content
        with file(filename, 'wb') as f:
            f.write(content)
        self._fifo.append(filename)
        if len(self._fifo) > self._max_cached:
            try:
                print >>sys.stderr, "purging %s cache" % (self._prefix,)
                os.unlink(self._fifo.pop(0))
            except:
                pass
        return content

# Cache shortened links. This cache grows forever, but that
# should not be a problem: Every configuration change made
# to the setup restarts the service. And the expected number
# of cache entries isn't too big to be a real problem anyway.
SHORTLINK_CACHE = {}

def render_short_link_qr_png(url):
    short_url = SHORTLINK_CACHE.get(url)
    if not short_url:
        r = http.post(
            url = 'https://s.newyorker.de/api/shorten',
            data = {
                'url': url,
            },
            timeout = 5,
        )
        r.raise_for_status()
        short_url = r.json()['shortUrl']
        print >>sys.stderr, 'new short_url is %s' % (short_url,)
        SHORTLINK_CACHE[url] = short_url
    else:
        print >>sys.stderr, 'using cached short_url %s' % (short_url,)

    qr = qrcode.QRCode(
        error_correction = qrcode.constants.ERROR_CORRECT_L,
        box_size = 10,
        border = 4,
    )
    qr.add_data(short_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="transparent")

    qr_code = StringIO()
    img.save(qr_code, format='png')
    return qr_code.getvalue()

class SlotUpdater(object):
    def __init__(self, item_type, refresh_interval):
        self._item_type = item_type
        self._refresh_interval = refresh_interval

        with file('config.json', 'rb') as f:
            config = json.load(f)
        self._slots = []
        for idx, item in enumerate(config['playlist']):
            if item['type'] != self._item_type:
                continue

            slot_uuid = item['uuid']
            if not slot_uuid:
                slot_uuid = 'slot-%d' % (idx+1)
            self._slots.append((
                slot_uuid,
                item['settings'],
            ))

        self._country = config['country']
        self._language = config['language']
        self._endpoint = config['endpoint']

    def before_update(self):
        pass

    def tick(self):
        c = DistributedDataClient(self._item_type)
        if not TESTMODE:
            if not c.is_master:
                time.sleep(5)
                return

        self.before_update()

        c.create_version()

        slots = {}
        for slot_uuid, slot_settings in self._slots:
            c.set_prefix('%s-%s-' % (self._item_type, slot_uuid))
            slot_settings_with_meta = dict(slot_settings)
            slot_settings_with_meta['_slot_uuid'] = slot_uuid
            slots[slot_uuid] = self.generate_slot(c, slot_settings_with_meta)

        if TESTMODE:
            import pprint, sys
            print "\nGenerated Slots:\n================\n"
            pprint.pprint(slots)
            sys.exit(0)

        c.set_prefix('')
        c.add_json("%s.json" % self._item_type,
            slots = slots,
        )
        c.commit()

    def run_forever(self):
        while 1:
            cycle_started = time.time()
            self.tick()
            elapsed = time.time() - cycle_started
            sleep_for = self._refresh_interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
