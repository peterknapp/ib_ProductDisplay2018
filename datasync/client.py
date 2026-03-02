import traceback, zipfile, json
import requests
from cStringIO import StringIO

PORT = 4242

class DistributedDataClient(object):
    def __init__(self, key):
        self._key = key
        self._zip = None
        self._mem = None
        self._prefix = ''

    @classmethod
    def join(cls, group, num_nodes):
        try:
            r = requests.post('http://127.0.0.1:%d/join/%s/%d' % (
                PORT, group, num_nodes
            ), timeout=2)
            r.raise_for_status()
            return r.content == 'ok'
        except:
            traceback.print_exc()
            return False

    @property
    def is_master(self):
        try:
            r = requests.get('http://127.0.0.1:%d/is_master' % (
                PORT,
            ), timeout=2)
            r.raise_for_status()
            return r.content == 'yes'
        except:
            traceback.print_exc()
            return False

    def discard_version(self):
        if self._zip is None:
            return
        self._zip.close()
        self._mem = None
        self._zip = None

    def create_version(self):
        self.discard_version()
        self._mem = StringIO()
        self._zip = zipfile.ZipFile(self._mem, 'w')

    def set_prefix(self, prefix):
        self._prefix = prefix

    def add_file(self, filename, filedata):
        filename = self._prefix + filename
        self._zip.writestr(filename, filedata)
        return filename

    def add_json(self, filename, **data):
        filename = self._prefix + filename
        self._zip.writestr(filename, json.dumps(data))
        return filename

    def commit(self):
        try:
            self._zip.close()
            self._mem.seek(0)
            r = requests.post('http://127.0.0.1:%d/update/%s' % (
                PORT, self._key
            ), timeout=2, data=self._mem)
            r.raise_for_status()
            return True
        except:
            traceback.print_exc()
            return False
        finally:
            self.discard_version()
