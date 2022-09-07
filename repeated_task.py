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
            repeat_job = self._queue.get()

            if isinstance(repeat_job, RepeatJob):
                worker_thread = self._workers.get(repeat_job.uniq_id, None)
                if worker_thread and worker_thread.is_alive():
                    logging.info(f"Reset worker for {repeat_job.uniq_id}")
                    worker_thread.reset(repeat_job.job)
                else:
                    logging.info(f"Create new worker for {repeat_job.uniq_id}")
                    message_reloader = RepeatJobThread(repeat_job)
                    self._workers[repeat_job.uniq_id] = message_reloader
                    message_reloader.start()
            self._queue.task_done()

    def schedule(self, reload_message_job: RepeatJob):
        self._queue.put(reload_message_job)


class RepeatJobThread(Thread):

    def __init__(self, repeat_job: RepeatJob):
        Thread.__init__(self, name=f"repeat-job-{repeat_job.uniq_id}", daemon=True)
        self._uniq_id = repeat_job.uniq_id
        self._repeat_interval = repeat_job.repeat_interval
        self._repeat_count = repeat_job.repeat_count
        self._job = repeat_job.job
        self._execute_job_counter = 0

    def run(self):
        while self._execute_job_counter < self._repeat_count:
            time.sleep(self._repeat_interval.total_seconds())
            logging.info(f"Execute job for {self._uniq_id}")
            try:
                self._job()
            except Exception as e:
                logging.error(f"RepeatJob {self._uniq_id} error. {e}")
            self._execute_job_counter += 1

    def reset(self, job: Callable[[], None]):
        self._execute_job_counter = self._repeat_count
        self._job = job
