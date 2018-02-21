import json
import logging
import logging.config
import multiprocessing
import os

from pycoshark.utils import get_base_argparser

from memeshark.config import Config
from memeshark.memeshark import MemeSHARK


def setup_logging(default_path=os.path.dirname(os.path.realpath(__file__))+"/loggerConfiguration.json",
                  default_level=logging.INFO):
        """
        Setup logging configuration

        :param default_path: path to the logger configuration
        :param default_level: defines the default logging level if configuration file is not found(default:logging.INFO)
        """
        path = default_path
        if os.path.exists(path):
            with open(path, 'rt') as f:
                config = json.load(f)
            logging.config.dictConfig(config)
        else:
            logging.basicConfig(level=default_level)


def start():
    """
    Starts the application. First parses the different command line arguments and then it gives these to
    :class:`~memeshark.memeshark.MemeSHARK`
    """
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting memeSHARK...")

    parser = get_base_argparser('Plugin to remove code entities and code groups that did not change in a revision.', '0.1.0')
    parser.add_argument('--debug', help='Sets the debug level.', default='DEBUG',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    parser.add_argument('-n', '--project-name', help='Name of the project to compress.', required=True)

    args = parser.parse_args()
    cfg = Config(args)

    logger.debug("Got the following config: %s" % cfg)
    meme_shark = MemeSHARK()
    meme_shark.start(cfg)


if __name__ == "__main__":
    start()