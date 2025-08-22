from .storage import PersistentStorage

import json
import os

class WorldState:
    def __init__(self, storage_file="world_state.json"):
        self.storage_file = storage_file
        self.accounts = self.load_state()

    def create_account(self, address):
        if address not in self.accounts:
            self.accounts[address] = {
                'balance': 0,
                'storage': {},
                'code': []
            }
            self.save_state()

    def set_contract_code(self, address, code):
        self.create_account(address)
        self.accounts[address]['code'] = list(code)  # Save as list of ints
        self.save_state()

    def get_contract_code(self, address):
        return bytes(self.accounts.get(address, {}).get('code', []))

    def get_storage(self, address):
        return self.accounts.get(address, {}).get('storage', {})

    def update_storage(self, address, storage):
        self.create_account(address)
        self.accounts[address]['storage'] = {
            str(k): v for k, v in storage.items()
        }
        self.save_state()

    def save_state(self):
        with open(self.storage_file, 'w') as f:
            json.dump(self.accounts, f, indent=2)

    def load_state(self):
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r') as f:
                return json.load(f)
        return {}

