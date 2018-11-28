import logging
import logging.config

from pycoshark.utils import get_base_argparser

from memeshark.config import Config, setup_logging
from memeshark.memeshark import MemeSHARK


def start():
    """
    Starts the application. First parses the different command line arguments and then it gives these to
    :class:`~memeshark.memeshark.MemeSHARK`
    """
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting memeSHARK...")

    parser = get_base_argparser('Plugin to remove code entities and code groups that did not change in a revision.', '0.1.0')
    parser.add_argument('--log-level', help='Sets the debug level.', default='DEBUG',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    parser.add_argument('-n', '--project-name', help='Name of the project to compress.', required=True)
    parser.add_argument('-c', '--processes', help='Number of parallel processes.', default=1)

    args = parser.parse_args()
    cfg = Config(args)

    logger.debug("Got the following config: %s" % cfg)
    meme_shark = MemeSHARK()
    meme_shark.start(cfg)


if __name__ == "__main__":
    start()