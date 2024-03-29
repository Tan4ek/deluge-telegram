from distutils.util import strtobool
from typing import Dict, List

from deluge_client import DelugeRPCClient


class DelugeService:
    # list of deluge fields - https://libtorrent.org/single-page-ref.html

    def __init__(self, config):
        self._deluge_client = DelugeRPCClient(config.get('deluge', 'host'),
                                              int(config.get('deluge', 'port')),
                                              config.get('deluge', 'username'),
                                              config.get('deluge', 'password'),
                                              decode_utf8=True)
        self._deluge_client.connect()
        self._label_enable = False
        try:
            self._label_enable = bool(strtobool(config.get('deluge', 'LabelEnable', fallback='false')))
        except ValueError:
            pass

        self._label_id = config.get('deluge', 'LabelId', fallback=None)

        if self._is_label_enabled():
            self.create_label(self._label_id)

    def add_torrent_magnet(self, magnet_url: str) -> str:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L556
        torrent_id = self._deluge_client.core.add_torrent_magnet(magnet_url, {})
        if self._is_label_enabled():
            self.set_torrent_label(torrent_id, self._label_id)
        return torrent_id

    def add_torrent_file(self, file_name: str, file_base64_str: str) -> str:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L407
        torrent_id = self._deluge_client.core.add_torrent_file(file_name, file_base64_str, {})
        if self._is_label_enabled():
            self.set_torrent_label(torrent_id, self._label_id)
        return torrent_id

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

    def torrents_status(self, torrent_ids: List[str]) -> List[Dict[str, str]]:
        fields = ['name', 'state', 'progress', 'completed_time', 'time_added', 'total_wanted', 'total_done']
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L772
        torrents_dict = self._deluge_client.core.get_torrents_status({"id": [i for i in torrent_ids]}, fields)
        return DelugeService._dict_key_to_obj(torrents_dict)

    def labeled_torrents(self) -> List[Dict[str, str]]:
        if self._is_label_enabled():
            fields = ['name', 'state', 'progress', 'completed_time', 'time_added', 'total_wanted', 'total_done']
            labeled_torrents = self._deluge_client.core.get_torrents_status({'label': self._label_id}, fields)
            return DelugeService._dict_key_to_obj(labeled_torrents)
        else:
            return []

    def stop_download_torrents(self):
        self._deluge_client.core.set_config({'max_download_speed': "0"})

    def resume_download_torrents(self):
        self._deluge_client.core.set_config({'max_download_speed': "-1"})

    def free_space_bytes(self) -> int:
        # https://github.com/deluge-torrent/deluge/blob/deluge-2.0.3/deluge/core/core.py#L1235
        return self._deluge_client.core.get_free_space()

    def _is_label_enabled(self) -> bool:
        if self._label_enable and self._label_id:
            return True
        else:
            return False

    @staticmethod
    def _dict_key_to_obj(d) -> List[Dict[str, str]]:
        if not d or not len(d):
            return []
        torrents = []
        for key, value in d.items():
            value['_id'] = key
            torrents.append(value)
        return torrents

    def disconnect(self):
        self._deluge_client.disconnect()
