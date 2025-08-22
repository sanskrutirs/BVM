# bvm/storage.py
import json
import os

class PersistentStorage:
    def __init__(self, storage_file='bvm_storage.json'):
        self.storage_file = storage_file
        self.cache = {}
        self._load_storage()

    def _load_storage(self):
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r') as f:
                self.cache = json.load(f)

    def _save_storage(self):
        with open(self.storage_file, 'w') as f:
            json.dump(self.cache, f)

    def get(self, key, default=None):
        return self.cache.get(str(key), default)

    def put(self, key, value):
        self.cache[str(key)] = value
        self._save_storage()

    def delete(self, key):
        if str(key) in self.cache:
            del self.cache[str(key)]
            self._save_storage()
