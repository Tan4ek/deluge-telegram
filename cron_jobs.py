import logging
from collections import defaultdict

from telegram import Bot, ParseMode

from deluge_service import DelugeService
from repository import TorrentStatus, Repository, COMMON_FOR_ALL_TG_USER_ID


class CronJob:

    def interval_seconds(self) -> int:
        pass

    def run(self):
        pass


class DeleteExpiredCacheJob(CronJob):
    _CHECK_EXPIRED_CACHE_INTERVAL_SECONDS = 60 * 60

    def __init__(self, repository: Repository):
        super().__init__()
        self._repository = repository

    def interval_seconds(self) -> int:
        return self._CHECK_EXPIRED_CACHE_INTERVAL_SECONDS

    def run(self):
        delete_lines = self._repository.delete_expired_cache()
        logging.debug(f'deleted expired cache rows {delete_lines}')


class NotDownloadedTorrentsStatusCheckJob(CronJob):
    _CHECK_DOWNLOADED_TORRENT_INTERVAL_SECONDS = 60
    _TORRENT_CHECK_NO_DATA_RETRY = defaultdict(lambda: 0)

    def __init__(self, repository: Repository, bot: Bot, deluge_service: DelugeService):
        super().__init__()
        self._repository = repository
        self._bot = bot
        self._deluge_service = deluge_service

    def interval_seconds(self) -> int:
        return self._CHECK_DOWNLOADED_TORRENT_INTERVAL_SECONDS

    def run(self):
        for s in self._repository.not_downloaded_torrents():
            telegram_user_id = s['tg_user_id']
            deluge_torrent_id = s['deluge_torrent_id']
            old_status = s['deluge_torrent_status']
            ts = self._deluge_service.torrent_status(deluge_torrent_id)
            if ts and ts['name']:
                torrent_name = ts['name']
                deluge_state = ts['state']

                if str(deluge_state) == TorrentStatus.DOWNLOADED.value:
                    if telegram_user_id != COMMON_FOR_ALL_TG_USER_ID:
                        self._bot.send_message(chat_id=telegram_user_id, text=f"Download `{torrent_name}` completed",
                                               parse_mode=ParseMode.MARKDOWN)
                    self._repository.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADED)
                if str(deluge_state) == TorrentStatus.DOWNLOADING.value:
                    self._repository.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADING)
            else:
                logging.warning(f"Skipping check status for {deluge_torrent_id}. No data.")
                if NotDownloadedTorrentsStatusCheckJob._TORRENT_CHECK_NO_DATA_RETRY[deluge_torrent_id] > 3:
                    self._repository.delete_torrent(deluge_torrent_id)
                    NotDownloadedTorrentsStatusCheckJob._TORRENT_CHECK_NO_DATA_RETRY.pop(deluge_torrent_id, None)
                    logging.warning(f"Delete torrent '{deluge_torrent_id}'. Looks like it deleted from deluge.")
                else:
                    NotDownloadedTorrentsStatusCheckJob._TORRENT_CHECK_NO_DATA_RETRY[deluge_torrent_id] += 1


class ScanCommonTorrents(CronJob):
    _CHECK_COMMON_TORRENTS_INTERVAL_SECONDS = 60

    def __init__(self, repository: Repository, deluge_service: DelugeService):
        super().__init__()
        self._repository = repository
        self._deluge_service = deluge_service

    def interval_seconds(self) -> int:
        return self._CHECK_COMMON_TORRENTS_INTERVAL_SECONDS

    def run(self):
        labeled_torrents = self._deluge_service.labeled_torrents()
        for labeled_torrent in labeled_torrents:
            torrent_id = labeled_torrent['_id']
            if not self._repository.torrent_exist_by_deluge_id(torrent_id):
                self._repository.create_common_torrent(torrent_id)
