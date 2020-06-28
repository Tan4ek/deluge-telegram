import threading
import time

import telegram
from deluge_client import DelugeRPCClient
from telegram import Bot

from safe_schedule import SafeScheduler
from user_service import TorrentStatus
from user_service import UserService

_CHECK_DOWNLOADED_TORRENT_INTERVAL_SECONDS = 60


class ScheduleThread(threading.Thread):

    def __init__(self, user_service: UserService, bot: Bot, deluge_client: DelugeRPCClient):
        super().__init__()
        self._user_service = user_service
        self._bot = bot
        self._deluge_client = deluge_client
        self.cease_continuous_run = threading.Event()

    def not_downloaded_torrents_status_check_job(self):
        x = self._user_service.not_downloaded_torrents()
        for s in x:
            telegram_user_id = s[0]
            deluge_torrent_id = s[1]
            old_status = s[2]
            ts = self._deluge_client.core.get_torrent_status(deluge_torrent_id, ['name', 'state'])
            torrent_name = ts['name']
            deluge_state = ts['state']

            if str(deluge_state) == TorrentStatus.DOWNLOADED.value:
                self._bot.send_message(chat_id=telegram_user_id, text=f"Download `{torrent_name}` completed",
                                       parse_mode=telegram.ParseMode.MARKDOWN)
                self._user_service.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADED)
            if str(deluge_state) == TorrentStatus.DOWNLOADING.value:
                self._user_service.update_status(deluge_torrent_id, TorrentStatus.DOWNLOADING)

    def run(self):
        scheduler = SafeScheduler()
        scheduler.every(_CHECK_DOWNLOADED_TORRENT_INTERVAL_SECONDS).seconds\
            .do(self.not_downloaded_torrents_status_check_job)
        scheduler.run_pending()
        while not self.cease_continuous_run.is_set():
            scheduler.run_pending()
            time.sleep(1)

    def stop(self):
        self.cease_continuous_run.set()
