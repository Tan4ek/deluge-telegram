import sqlite3
from datetime import datetime
from enum import Enum


# https://github.com/deluge-torrent/deluge/blob/develop/deluge/core/torrent.py#L51
class TorrentStatus(Enum):
    CREATED = 'Checking'
    DOWNLOADING = 'Downloading'
    DOWNLOADED = 'Seeding'
    ERROR = 'Error'
    UNKNOWN_STUB = '_unknown_stub_'

    def __str__(self):
        return self.name

    @staticmethod
    def get_by_value_safe(value: str):
        try:
            return TorrentStatus(value)
        except ValueError:
            return TorrentStatus.UNKNOWN_STUB


class Repository:
    _TORRENT_TABLE = "torrents"
    _CACHE_TABLE = "cache"

    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.__ini_db()

    def __ini_db(self):
        sql_create_auth_token = f"""CREATE TABLE IF NOT EXISTS {self._TORRENT_TABLE} (
        id integer PRIMARY KEY,
        create_time text NOT NULL,
        last_update_time text NOT NULL,
        tg_user_id integer NOT NULL,
        deluge_torrent_id text NOT NULL,
        deluge_torrent_status text NOT NULL ,
        UNIQUE(tg_user_id,deluge_torrent_id) )
        """

        sql_create_cache = f"""CREATE TABLE IF NOT EXISTS {self._CACHE_TABLE} (
        key text NOT NULL,
        value text NOT NULL,
        create_time text NOT NULL,
        ttl_seconds integer NOT NULL)
        """

        sql_cache_index = f"CREATE UNIQUE INDEX IF NOT EXISTS idx_key ON {self._CACHE_TABLE} (key);"

        for sql in [sql_create_auth_token, sql_create_cache, sql_cache_index]:
            self.conn.execute(sql)

    def create_torrent(self, tg_user_id: int, deluge_torrent_id: str, override_on_exist=False):
        x = (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), tg_user_id, deluge_torrent_id,
             str(TorrentStatus.CREATED))
        with self.conn:
            self.conn.execute(
                f"INSERT {'OR REPLACE' if override_on_exist else ''} INTO {self._TORRENT_TABLE} "
                f"(create_time, last_update_time, tg_user_id, deluge_torrent_id, "
                f"deluge_torrent_status) VALUES (?,?,?,?,?)",
                x)

    def update_status(self, deluge_torrent_id: str, new_status: TorrentStatus):
        if new_status is None or not isinstance(new_status, TorrentStatus):
            raise ValueError("invalid 'torrent_status' to update")
        with self.conn:
            self.conn.execute(f"UPDATE {self._TORRENT_TABLE} SET deluge_torrent_status = '{new_status}',"
                              f"last_update_time='{datetime.utcnow().isoformat()}'"
                              f"WHERE deluge_torrent_id = '{deluge_torrent_id}'")

    def all_user_torrents(self, tg_user_id: int, limit=20):
        assert limit > 0, "negative limit"
        c = self.conn.cursor()
        r = c.execute(f"SELECT id, create_time, last_update_time, tg_user_id, deluge_torrent_id, deluge_torrent_status "
                      f"FROM {self._TORRENT_TABLE} "
                      f"WHERE tg_user_id = {tg_user_id} "
                      f"LIMIT {limit}")
        return c.fetchmany(limit)

    def not_downloaded_torrents(self):
        c = self.conn.cursor()
        r = c.execute(f"SELECT tg_user_id, deluge_torrent_id, deluge_torrent_status FROM {self._TORRENT_TABLE} "
                      f"WHERE deluge_torrent_status IS NOT '{TorrentStatus.DOWNLOADED}'")
        return c.fetchall()

    def create_cache(self, key, value, ttl_seconds=60 * 60 * 24 * 30, override_on_exist=False) -> None:
        x = (key, value, datetime.utcnow().isoformat(), ttl_seconds)
        with self.conn:
            self.conn.execute(
                f"INSERT {'OR REPLACE' if override_on_exist else ''} INTO {self._CACHE_TABLE} "
                f"(key, value, create_time, ttl_seconds) VALUES (?,?,?,?)",
                x)

    def get_cache(self, key) -> dict:
        c = self.conn.cursor()
        r = c.execute(f"SELECT key, value, create_time, ttl_seconds FROM {self._CACHE_TABLE} "
                      f"WHERE key = '{key}'")
        return c.fetchone()

    def delete_expired_cache(self) -> int:
        with self.conn:
            self.conn.execute(
                f"DELETE FROM {self._CACHE_TABLE} "
                f"WHERE strftime('%s',create_time) + ttl_seconds - strftime('%s','now')  < 0")
            return self.conn.total_changes

    def disconnect(self):
        self.conn.close()