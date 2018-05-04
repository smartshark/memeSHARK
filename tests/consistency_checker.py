import argparse
import json
import logging
import logging.config
import os
import sys

from dictdiffer import diff
from mongoengine import connect, DoesNotExist
from mongoengine.context_managers import switch_db
from pycoshark.mongomodels import Commit, CodeEntityState, Project, VCSSystem
from pycoshark.utils import create_mongodb_uri_string


def setup_logging(default_path=os.path.dirname(os.path.realpath(__file__)) + "/../loggerConfiguration.json",
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
    Compares the commits and code_entity_states of two MongoDBs, whereas the first MongoDB is
    is condensed with the memeSHARK and the second MongoDB is verbose.
    """
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting consistency checker...")

    parser = argparse.ArgumentParser(description='DB consistency checker.')

    parser.add_argument('-v', '--version', help='Shows the version', action='version', version='0.1.0')
    parser.add_argument('-U1', '--db-user1', help='Database user name', default=None)
    parser.add_argument('-P1', '--db-password1', help='Database user password', default=None)
    parser.add_argument('-DB1', '--db-database1', help='Database name', default='smartshark')
    parser.add_argument('-H1', '--db-hostname1', help='Name of the host, where the database server is running',
                        default='localhost')
    parser.add_argument('-p1', '--db-port1', help='Port, where the database server is listening', default=27017,
                        type=int)
    parser.add_argument('-a1', '--db-authentication1', help='Name of the authentication database', default=None)
    parser.add_argument('--ssl1', help='Enables SSL', default=False, action='store_true')

    parser.add_argument('-U2', '--db-user2', help='Database user name', default=None)
    parser.add_argument('-P2', '--db-password2', help='Database user password', default=None)
    parser.add_argument('-DB2', '--db-database2', help='Database name', default='smartshark_backup')
    parser.add_argument('-H2', '--db-hostname2', help='Name of the host, where the database server is running',
                        default='localhost')
    parser.add_argument('-p2', '--db-port2', help='Port, where the database server is listening', default=27017,
                        type=int)
    parser.add_argument('-a2', '--db-authentication2', help='Name of the authentication database', default=None)
    parser.add_argument('--ssl2', help='Enables SSL', default=False, action='store_true')

    parser.add_argument('--debug', help='Sets the debug level.', default='DEBUG',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    parser.add_argument('-n', '--project-name', help='Name of the project to compress.', default=None)

    args = parser.parse_args()

    logger.info(args)

    logger.info("connecting to database 1 (condensed)...")
    uri1 = create_mongodb_uri_string(args.db_user1, args.db_password1, args.db_hostname1, args.db_port1,
                                     args.db_authentication1, args.ssl1)
    logger.info(uri1)
    connect(args.db_database1, host=uri1, alias='default')

    logger.info("connecting to database 2 (verbose)...")
    uri2 = create_mongodb_uri_string(args.db_user2, args.db_password2, args.db_hostname2, args.db_port2,
                                     args.db_authentication2, args.ssl2)
    logger.info(uri2)
    connect(args.db_database2, host=uri2, alias='db-verbose')

    # fetch all verbose commmits
    commits_verbose = []
    with switch_db(Commit, 'db-verbose') as CommitVerbose:
        if args.project_name is None:
            # no project specified, fetch all commits
            commit_objects = CommitVerbose.objects()
        else:
            # fetch only commits for selected project
            try:
                project_id = Project.objects(name=args.project_name).get().id
            except DoesNotExist:
                logger.error('Project %s not found!' % args.project_name)
                sys.exit(1)
            vcs_systems = VCSSystem.objects(project_id=project_id).get().id
            logger.info("vcs_system_id: %s", vcs_systems)
            commit_objects = Commit.objects(vcs_system_id=vcs_systems)

        # Update for only selecting single projects should be here
        for cur_commit_verbose in commit_objects:
            commits_verbose.append(cur_commit_verbose)
    num_commits_verbose = len(commits_verbose)
    logger.info("num commits verbose: %i", num_commits_verbose)
    for commit_nr, commit_verbose in enumerate(commits_verbose):
        logger.info("processing commit %s (%i / %i)", commit_verbose.id, commit_nr + 1, num_commits_verbose)
        # fetch verbose CES
        ces_verbose = {}
        ces_verbose_by_id = {}
        with switch_db(CodeEntityState, 'db-verbose') as CodeEntityStateVerbose:
            for cur_ces_verbose in CodeEntityStateVerbose.objects(commit_id=commit_verbose.id):
                ces_verbose[cur_ces_verbose.long_name + str(cur_ces_verbose.file_id)] = cur_ces_verbose
                ces_verbose_by_id[cur_ces_verbose.id] = cur_ces_verbose

        # fetch same commit in condensed DB
        commit_condensed = None
        with switch_db(Commit, 'default') as CommitCondensed:
            commit_condensed = CommitCondensed.objects(id=commit_verbose.id).get()

        # fetch CES from condensed DB
        ces_condensed = {}
        ces_condensed_by_id = {}
        with switch_db(CodeEntityState, 'default') as CodeEntityStateCondensed:
            for ces_id in commit_condensed.code_entity_states:
                cur_ces_condensed = CodeEntityStateCondensed.objects(id=ces_id).get()
                ces_condensed[cur_ces_condensed.long_name + str(cur_ces_condensed.file_id)] = cur_ces_condensed
                ces_condensed_by_id[cur_ces_condensed.id] = cur_ces_condensed

        logger.info("num CES verbose  : %i", len(ces_verbose.keys()))
        logger.info("num CES condensed: %i", len(ces_condensed.keys()))

        ces_unequal = 0
        # compare CES
        for long_name_verbose, cur_ces_verbose in ces_verbose.items():
            if long_name_verbose not in ces_condensed:
                logger.error("CES with long_name %s not found in condensed DB!", long_name_verbose)
                ces_unequal += 1
                continue

            cur_ces_condensed = ces_condensed[long_name_verbose]
            old, new = compare_dicts(cur_ces_verbose, cur_ces_condensed,
                                             {'id', 's_key', 'commit_id', 'ce_parent_id', 'cg_ids'})
            if len(new.keys()) > 0 or len(old.keys()) > 0:
                logger.error("CES with long_name %s (id verbose: %s /id condensed %s) not equal!", long_name_verbose,
                             cur_ces_verbose.id, cur_ces_condensed.id)
                logger.error("verbose  : %s", old)
                logger.error("condensed: %s", new)
                ces_unequal += 1
                continue

            # check if CES parent is equal
            ces_parent_verbose = ces_verbose_by_id[cur_ces_verbose.id]
            ces_parent_condensed = ces_condensed_by_id[cur_ces_condensed.id]
            old, new = compare_dicts\
                (ces_parent_verbose, ces_parent_condensed,
                                             {'id', 's_key', 'commit_id', 'ce_parent_id', 'cg_ids'})
            if len(new.keys()) > 0 or len(old.keys()) > 0:
                logger.error("ce_parent of CES with long_name %s not equal!", long_name_verbose)
                logger.error("verbose  : %s", old)
                logger.error("condensed: %s", new)
                ces_unequal += 1
                continue

        logger.info("num CES from verbose not matched: %i", ces_unequal)


def compare_dicts(obj1, obj2, excluded_keys):
    """
    Compares to dicts to each other, and returns the differences.
    :param obj1: first dict
    :param obj2: second dict
    :param excluded_keys: keys that are ignored
    :return: two dicts: old for the state in the obj1, new for the state in obj2 in case of differences
    """
    keys = obj1._fields_ordered
    old, new = {}, {}
    for key in keys:
        if key in excluded_keys:
            continue
        try:
            value1 = getattr(obj1, key)
            value2 = getattr(obj2, key)
            if value1 != value2:
                if isinstance(value1, dict) and isinstance(value2, dict):
                    result = list(diff(value1, value2))
                    if len(result) > 0:
                        old.update({key: getattr(obj1, key)})
                        new.update({key: getattr(obj2, key)})
                else:
                    old.update({key: getattr(obj1, key)})
                    new.update({key: getattr(obj2, key)})
        except KeyError:
            old.update({key: getattr(obj1, key)})

    return old, new


if __name__ == "__main__":
    start()
