
from typing import Dict, List

from deluge_client import DelugeRPCClient


class DelugeService:

    def __init__(self, config):
        self._deluge_client = DelugeRPCClient(config.get('deluge', 'host'),
                                int(config.get('deluge', 'port')),
                                config.get('deluge', 'username'),
                                config.get('deluge', 'password'),
                                decode_utf8=True)
        self._deluge_client.connect()

    def add_torrent_magnet(self, magnet_url: str) -> str:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L556
        return self._deluge_client.core.add_torrent_magnet(magnet_url, {})

    def add_torrent_file(self, file_name: str, file_base64_str: str) -> str:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L407
        return self._deluge_client.core.add_torrent_file(file_name, file_base64_str, {})

    def create_label(self, label_id: str):
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/plugins/Label/deluge_label/core.py#L178
        try:
            self._deluge_client.label.add(label_id)
        except Exception as e:
            if 'Exception: Label already exists' not in str(e):
                raise e

    def delete_label(self, label_id: str):
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/plugins/Label/deluge_label/core.py#L193
        try:
            self._deluge_client.label.remove(label_id)
        except Exception as e:
            if 'Exception: Unknown Label' not in str(e):
                raise e

    def get_labels(self) -> List[str]:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/plugins/Label/deluge_label/core.py#L173
        return self._deluge_client.label.get_labels()

    def set_torrent_label(self, torrent_id: str, label_id: str):
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/plugins/Label/deluge_label/core.py#L312
        self._deluge_client.label.set_torrent(torrent_id, label_id)

    def delete_torrent(self, torrent_id: str):
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L574
        self._deluge_client.core.remove_torrent(torrent_id, False)

    def torrent_name_by_id(self, torrent_id: str) -> str:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L758
        return self._deluge_client.core.get_torrent_status(torrent_id, ['name'])['name']

    def torrent_status(self, torrent_id: str) -> Dict[str, str]:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L758
        return self._deluge_client.core.get_torrent_status(torrent_id, ['name', 'state'])

    def disconnect(self):
        self._deluge_client.disconnect()
