import logging

from telegram import Bot, ParseMode

from deluge_service import DelugeService
from repository import TorrentStatus, Repository


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

    def __init__(self, repository: Repository, bot: Bot, deluge_service: DelugeService):
        super().__init__()
        self._repository = repository
        self._bot = bot
        self._deluge_service = deluge_service

    def interval_seconds(self) -> int:
        return self._CHECK_DOWNLOADED_TORRENT_INTERVAL_SECONDS

    def run(self):
        for s in self._repository.not_downloaded_torrents():
            telegram_user_id = s[0]
            deluge_torrent_id = s[1]
            old_status = s[2]
            ts = self._deluge_service.torrent_status(deluge_torrent_id)
            torrent_name = ts['name']
            deluge_state = ts['state']

            if str(deluge_state) == TorrentStatus.DOWNLOADED.value:
                self._bot.send_message(chat_id=telegram_user_id, text=f"Download `{torrent_name}` completed",
                                       parse_mode=ParseMode.MARKDOWN)
                self._repository.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADED)
            if str(deluge_state) == TorrentStatus.DOWNLOADING.value:
                self._repository.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADING)
