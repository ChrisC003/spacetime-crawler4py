from configparser import ConfigParser
from argparse import ArgumentParser
import multiprocessing as mp
import sys

from utils.server_registration import get_cache_server
from utils.config import Config
from crawler import Crawler
import generate_report
import record


# we test on mac so add this for multiprocessing
def configure_multiprocessing():
    if sys.platform != "win32":
        try:
            mp.set_start_method("fork")
        except RuntimeError:
            pass


def main(config_file, restart):
    configure_multiprocessing()
    cparser = ConfigParser()
    cparser.read(config_file)
    config = Config(cparser)
    config.cache_server = get_cache_server(config, restart)
    crawler = Crawler(config, restart)
    crawler.start()
    
    # add for our test framework
    state_path = record.current_state_path()
    if state_path is not None:
        generate_report.generate_from_state(state_path)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--restart", action="store_true", default=False)
    parser.add_argument("--config_file", type=str, default="config.ini")
    args = parser.parse_args()
    main(args.config_file, args.restart)
