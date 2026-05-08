import os
import shelve
import time
from threading import Condition, RLock
from urllib.parse import urlparse
from utils import get_logger, get_urlhash, normalize
import scraper


class Frontier(object):
    def __init__(self, config, restart):
        self.logger = get_logger("FRONTIER")
        self.config = config
        scraper.set_crawler_config(config)
        self.to_be_downloaded = list()
        self.lock = RLock()
        self.url_available = Condition(self.lock)
        self.politeness = Condition(self.lock)
        self.active_workers = 0
        self.next_request_time = dict()
        
        if not os.path.exists(self.config.save_file) and not restart:
            # Save file does not exist, but request to load save.
            self.logger.info(
                f"Did not find save file {self.config.save_file}, "
                f"starting from seed.")
        elif os.path.exists(self.config.save_file) and restart:
            # Save file does exists, but request to start from seed.
            self.logger.info(
                f"Found save file {self.config.save_file}, deleting it.")
            os.remove(self.config.save_file)
        # Load existing save file, or create one if it does not exist.
        self.save = shelve.open(self.config.save_file)
        if restart:
            for url in self.config.seed_urls:
                self.add_url(url)
        else:
            # Set the frontier state with contents of save file.
            self._parse_save_file()
            if not self.save:
                for url in self.config.seed_urls:
                    self.add_url(url)

    def _parse_save_file(self):
        ''' This function can be overridden for alternate saving techniques. '''
        total_count = len(self.save)
        tbd_count = 0
        for url, completed in self.save.values():
            if not completed and scraper.is_valid(url):
                self.to_be_downloaded.append(url)
                tbd_count += 1
        self.logger.info(
            f"Found {tbd_count} urls to be downloaded from {total_count} "
            f"total urls discovered.")


    def get_tbd_url(self):
        with self.url_available:
            while not self.to_be_downloaded:
                if self.active_workers == 0:
                    return None
                self.url_available.wait()

            self.active_workers += 1
            return self.to_be_downloaded.pop()


    def add_url(self, url):
        url = normalize(url)
        urlhash = get_urlhash(url)
        with self.url_available:
            if urlhash not in self.save:
                self.save[urlhash] = (url, False)
                self.save.sync()
                self.to_be_downloaded.append(url)
                self.url_available.notify()


    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)
        with self.url_available:
            self.save[urlhash] = (url, True)
            self.save.sync()
            self.active_workers -= 1
            self.url_available.notify_all()


    def wait_for_politeness(self, url):
        """
        TA says every subdomain should have a politeness delay
        so we wait for the politeness delay before downloading the next URL
        from the same subdomain
        """
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if not domain:
            return

        with self.politeness:
            while True:
                now = time.monotonic()
                ready_at = self.next_request_time.get(domain, 0.0)
                wait_time = ready_at - now
                if wait_time <= 0:
                    self.next_request_time[domain] = now + self.config.time_delay
                    self.politeness.notify_all()
                    return
                self.politeness.wait(wait_time)
