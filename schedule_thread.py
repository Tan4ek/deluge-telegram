import threading
import time
from typing import List

from cron_jobs import CronJob
from safe_schedule import SafeScheduler


class ScheduleThread(threading.Thread):

    def __init__(self, cron_jobs: List[CronJob]):
        super().__init__()
        self._cron_jobs: List[CronJob] = cron_jobs
        self.cease_continuous_run = threading.Event()

    def run(self):
        scheduler = SafeScheduler()
        for cron_job in self._cron_jobs:
            scheduler.every(cron_job.interval_seconds()).seconds.do(cron_job.run)
        while not self.cease_continuous_run.is_set():
            scheduler.run_pending()
            time.sleep(1)

    def stop(self):
        self.cease_continuous_run.set()
