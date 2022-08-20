import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from queue import Queue
from threading import Thread
from typing import Dict, Callable


@dataclass
class RepeatJob:
    uniq_id: str
    job: Callable[[], None]
    repeat_interval: timedelta = timedelta(seconds=5)
    repeat_count: int = 5


class RepeatedJobManager(Thread):

    def __init__(self):
        Thread.__init__(self, name="repeated-job-manager", daemon=True)
        self._queue = Queue()
        self._workers: Dict[str, RepeatJobThread] = dict()

    def run(self):
        while True:
            v = self._queue.get()

            if isinstance(v, RepeatJob):
                worker_thread = self._workers.get(v.uniq_id, None)
                if worker_thread and worker_thread.is_alive():
                    logging.info(f"Reset worker for {v.uniq_id}")
                    worker_thread.reset(v.job)
                else:
                    logging.info(f"Create new worker for {v.uniq_id}")
                    message_reloader = RepeatJobThread(v.uniq_id, v.repeat_interval, v.repeat_count, v.job)
                    self._workers[v.uniq_id] = message_reloader
                    message_reloader.start()
            self._queue.task_done()

    def schedule(self, reload_message_job: RepeatJob):
        self._queue.put(reload_message_job)


class RepeatJobThread(Thread):

    def __init__(self, uniq_id: str, repeat_interval: timedelta, repeat_count: int, job: Callable[[], None]):
        Thread.__init__(self, name=f"job-{uniq_id}", daemon=True)
        self._repeat_interval = repeat_interval
        self._repeat_count = repeat_count
        self._job = job
        self._counter = 0

    def run(self):
        while self._counter < self._repeat_count:
            logging.info("refresh message")
            try:
                self._job()
            except Exception as e:
                logging.error(f"User message reloader error {e}")
            time.sleep(self._repeat_interval.total_seconds())
            self._counter += 1

    def reset(self, job: Callable[[], None]):
        self._counter = self._repeat_count
        self._job = job
