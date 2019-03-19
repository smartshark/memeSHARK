import logging
import multiprocessing
import sys
import time
import timeit
from math import isnan
from multiprocessing import Queue

import networkx as nx
from mongoengine import connect, DoesNotExist, connection
from mongoengine.base.datastructures import BaseDict
from pycoshark.mongomodels import Project, VCSSystem, Commit, CodeEntityState
from pycoshark.utils import create_mongodb_uri_string

from memeshark.config import setup_logging


class MemeSHARK(object):
    """
    Implements the merging of code group states and code entity states to remove unchanged duplicates from the database.
    """

    progress_counter = 0
    no_commits = 0
    ces_total = 0
    ces_deleted_total = 0

    def __init__(self):
        """
        Default constructor.
        """
        self.logger = logging.getLogger("main")
        pass

    def start(self, cfg):
        """
        Executes the memeSHARK.
        :param cfg: configuration object that is used
        """
        self.logger.setLevel(cfg.get_debug_level())
        start_time = timeit.default_timer()

        # Connect to mongodb
        uri = create_mongodb_uri_string(cfg.user, cfg.password, cfg.host, cfg.port, cfg.authentication_db,
                                        cfg.ssl_enabled)
        db_client = connect(cfg.database, host=uri, alias='default')

        # Get the id of the project for which the code entities shall be merged
        try:
            project_id = Project.objects(name=cfg.project_name).get().id
        except DoesNotExist:
            self.logger.error('Project %s not found!' % cfg.project_name)
            sys.exit(1)

        # Get the VCS systems for the project
        vcs_systems = VCSSystem.objects(project_id=project_id).get().id
        self.logger.info("vcs_system_id: %s", vcs_systems)

        # Get the commits for the project
        no_commits = Commit.objects(vcs_system_id=vcs_systems).count()

        # Create commit graph
        commit_graph = self._generate_graph(vcs_systems)

        # close connection to MongoDB - otherwise it will not work in the subprocesses
        db_client.close()
        connection._dbs = {}
        connection._connections = {}
        connection._connection_settings = {}

        # setup workers
        max_workers = cfg.processes
        task_queue = multiprocessing.JoinableQueue()
        started_tasks = multiprocessing.Queue()
        deleted_ces_queue = multiprocessing.Queue()
        total_ces_queue = multiprocessing.Queue()
        workers = [MemeSHARKWorker(commit_graph, cfg.database, uri, i, task_queue, started_tasks, deleted_ces_queue,
                                   total_ces_queue, no_commits) for i in range(0, max_workers)]

        self.logger.info("starting workers")
        for worker in workers:
            worker.start()
        time.sleep(5)  # brief wait for all processes to be ready

        # find nodes without predecessor or with multiple predecessors
        for i, node in enumerate(commit_graph):
            if len(commit_graph.pred[node]) != 1:
                self.logger.info("adding task for start of path with commit id: %s", node)
                task_queue.put(node)

        # wait task queue to be empty
        task_queue.join()

        self.logger.info("all tasks finished, terminating workers")
        for worker in workers:
            worker.terminate()

        # collect statistics
        ces_deleted_total = 0
        while not deleted_ces_queue.empty():
            ces_deleted_total += deleted_ces_queue.get()
        ces_total = 0
        while not total_ces_queue.empty():
            ces_total += total_ces_queue.get()

        self.logger.info("deleted %i of %i code entity states", ces_deleted_total, ces_total)
        elapsed = timeit.default_timer() - start_time
        self.logger.info("Execution time: %0.5f s" % elapsed)

    def _generate_graph(self, vcs_id):
        """
        Generates the commit graph for a VCS system.
        :param vcs_id: ID of the VCS system
        :return: the commit graph
        """
        g = nx.DiGraph()
        # first we add all nodes to the graph
        for c in Commit.objects.only('id').timeout(False).filter(vcs_system_id=vcs_id):
            g.add_node(c.id)

        # after that we draw all edges
        for c in Commit.objects.only('id', 'parents').timeout(False).filter(vcs_system_id=vcs_id):
            for p in c.parents:
                try:
                    p1 = Commit.objects.only('id').timeout(False).get(vcs_system_id=vcs_id, revision_hash=p)
                    g.add_edge(p1.id, c.id)
                except DoesNotExist:
                    self.logger.warning("parent of a commit is missing (commit id: %s - revision_hash: %s)", c.id, p)
                    pass
        return g


class MemeSHARKWorker(multiprocessing.Process):
    """
    Setup of workers
    :param commit_graph: the commit graph
    :param database: name of the MongoDB
    :param uri: URI of the MongoDB
    :param number: number of the worker
    :param task_queue: queue with tasks (i.e. starts of paths/branches)
    :param started_tasks: queue that counts the processed commits
    :param deleted_ces_queue: queue that counts the deleted CES for the project
    :param total_ces_queue: queue that counts the total CES for the project
    :param no_commits: number of commits of the project
    """

    def __init__(self, commit_graph, database, uri, number, task_queue, started_tasks, deleted_ces_queue,
                 total_ces_queue, no_commits):
        multiprocessing.Process.__init__(self)
        self.commit_graph = commit_graph
        self.database = database
        self.uri = uri
        self.alias = "worker%s" % number
        self.task_queue = task_queue
        self.no_commits = no_commits
        self.started_tasks = started_tasks
        self.deleted_ces_queue = deleted_ces_queue
        self.total_ces_queue = total_ces_queue

    def run(self):
        """
        Executes memeSHARK workers
        """
        setup_logging()
        self.logger = logging.getLogger(self.alias)
        connect(self.database, host=self.uri, alias='default')
        self.logger.info("ready")
        isIdle = False

        while True:
            if self.task_queue.empty():
                if not isIdle:
                    self.logger.info("queue empty - worker idle")
                    isIdle = True
                time.sleep(5)
                continue
            else:
                if isIdle:
                    self.logger.info("worker leaving idle state")
                    isIdle = False
                start_node = self.task_queue.get()

            if len(self.commit_graph.pred[start_node]) != 1:
                self.logger.info("start of path starting with node %s", start_node)
                self._merge_path(start_node)
            else:
                # fetch past state for parent
                self.logger.info("start merging for branch starting with node %s", start_node)
                ces_past_state = {}
                for pred in self.commit_graph.pred[start_node]:
                    pred_commit = Commit.objects(id=pred).get()
                    for i, ces in enumerate(CodeEntityState.objects(id__in=pred_commit.code_entity_states)):
                        ces_past_state[ces.long_name + ces.file_id.__str__()] = ces
                self._merge_node(start_node, ces_past_state)
            self.task_queue.task_done()

    def _merge_path(self, start_node):
        """
        Starts the merging of code entity states for a path in the commit graph.
        In the sense of the memeSHARK, a path starts with a commit that does not have exactly one parent and ends if a
        commit either has no successor or also not exactly one parent.
        :param start_node: node at the beginning of a path
        """
        self.started_tasks.put(1)
        current_progress = self.started_tasks.qsize()
        self.logger.info("merging for node %s (%i / %i)", start_node, current_progress, self.no_commits)
        ces_current_state = {}
        for ces in CodeEntityState.objects(commit_id=start_node):
            ces_current_state[ces.long_name + ces.file_id.__str__()] = ces

        self._add_ces_to_commit(start_node, ces_current_state)
        self.deleted_ces_queue.put(0)
        self.total_ces_queue.put(len(ces_current_state))

        successor = self.commit_graph.succ[start_node]

        for i, succnode in enumerate(successor):
            self._merge_node(succnode, ces_current_state)

    def _merge_node(self, node, ces_past_state):
        """
        Merges code entity states for the current node in the commit graph.
        :param node: the current node
        :param ces_past_state: the code entity states
        """
        while len(self.commit_graph.pred[node]) == 1:
            self.started_tasks.put(1)
            current_progress = self.started_tasks.qsize()
            self.logger.info("merging for node %s (%i / %i)", node, current_progress, self.no_commits)
            ces_current_state = {}  # contains CES that will be added to commit
            ces_map = {}  # for updating self-references
            ces_unchanged = []  # stores CES to be deleted
            ces_unchanged_parents = {}  # parents of the CES to be deleted
            ces_changed = []  # stores CES that are updated
            ces_this = {}  # map from IDs from current commit to CES

            # check if CES are already appended to commit, if yes fetch current state from commit and skip merging
            current_commit = Commit.objects(id=node).get()
            if len(current_commit.code_entity_states) > 0:
                self.logger.info("node %s already processed", node)
                # check if follower is also already processed
                is_processed = True
                for i, succnode in enumerate(self.commit_graph.succ[node]):
                    succ_commit = Commit.objects(id=succnode).get()
                    if not len(succ_commit.code_entity_states) > 0:
                        is_processed = False
                # only fetch CES if follower is not processed
                if not is_processed:
                    for i, ces in enumerate(CodeEntityState.objects(id__in=current_commit.code_entity_states)):
                        ces_current_state[ces.long_name + ces.file_id.__str__()] = ces
            else:
                for ces in CodeEntityState.objects(commit_id=node):
                    ces_this[ces.id] = ces
                    if ces.long_name + ces.file_id.__str__() not in ces_past_state:
                        ces_current_state[ces.long_name + ces.file_id.__str__()] = ces
                        ces_map[ces.id] = ces.id
                        ces_changed.append(ces.id)
                    else:
                        ces_past = ces_past_state[ces.long_name + ces.file_id.__str__()]
                        if not self._compare_dicts(ces_past, ces,
                                                   {'id', 's_key', 'commit_id', 'ce_parent_id', 'cg_ids'}):
                            ces_current_state[ces.long_name + ces.file_id.__str__()] = ces
                            ces_map[ces.id] = ces.id
                            ces_changed.append(ces.id)
                        else:
                            ces_current_state[ces.long_name + ces.file_id.__str__()] = ces_past
                            ces_map[ces.id] = ces_past.id
                            ces_unchanged.append(ces.id)
                            ces_unchanged_parents[ces.id] = ces.ce_parent_id

                # check if parent changed; if yes, the CES must be updated, too
                saved_children = True
                while saved_children:
                    saved_children = False
                    for ces in ces_unchanged:
                        if ces_unchanged_parents[ces] in ces_changed:
                            saved_children = True
                            ces_object = ces_this[ces]
                            ces_map[ces] = ces_object
                            ces_current_state[ces_object.long_name + ces_object.file_id.__str__()] = ces_object
                            ces_changed.append(ces)
                            ces_unchanged.remove(ces)

                self._add_ces_to_commit(node, ces_current_state)
                self._update_ces(node, ces_current_state, ces_unchanged, ces_map)
                self._delete_unchanged_ces(ces_unchanged, len(ces_current_state))

            # in case there is only on successor use iterative approach
            if len(self.commit_graph.succ[node]) == 1:
                ces_past_state = ces_current_state
                for i, succnode in enumerate(self.commit_graph.succ[node]):
                    node = succnode
            # add new job to queue for branches to enable parallelism for branches
            else:
                for i, succnode in enumerate(self.commit_graph.succ[node]):
                    num_pred = len(self.commit_graph.pred[succnode])
                    if num_pred == 1:
                        self.logger.info("Adding task for start of branch with commit id: %s", succnode)
                        self.task_queue.put(succnode)
                    else:
                        self.logger.info("Skipping merging for start of branch, because of #parents!=1 (%i): %s",
                                         num_pred, succnode)
                return

    def _add_ces_to_commit(self, node, current_state):
        """
        Adds a list of current code entity state IDs to a commit
        :param node: the commit
        :param current_state: the code entity stats
        """
        self.logger.info("adding code entity states to commit")
        commit = Commit.objects(id=node).get()
        ids = []
        for i, ces in current_state.items():
            ids.append(ces.id)
        commit.code_entity_states = ids
        commit.save()

    def _update_ces(self, node, ces_current_state, ces_unchanged, ces_map):
        """
        Updates the code entity states that are not deleted. This is required because the parents may change.
        :param node: the commit
        :param ces_current_state: the current code entity states
        :param ces_unchanged: the code entity states that did not change in a commit and are, therefore, deleted
        :param ces_map: a mapping of the IDs of code entity states in this commits to their representation that is kept
        """
        self.logger.info("updating broken parent references")
        for i, ces in ces_current_state.items():
            if ces.commit_id != node:
                continue  # skip CES from previous commits

            # updated CES references
            if ces.ce_parent_id in ces_unchanged:
                ces.ce_parent_id = ces_map[ces.ce_parent_id]
                ces.save()

    def _delete_unchanged_ces(self, ces_unchanged, no_ces):
        """
        Deletes the code entity states that did not change in the current commit.
        :param ces_unchanged: the IDs of the unchanged code entity states.
        :param no_ces: the total number of code entity states for this commit
        """
        self.logger.info("deleting %i of %i code entity states", len(ces_unchanged), no_ces)
        self.total_ces_queue.put(no_ces)
        self.deleted_ces_queue.put(len(ces_unchanged))
        CodeEntityState.objects(id__in=ces_unchanged).delete()

    def _compare_dicts(self, obj1, obj2, excluded_keys):
        """
        Compares to dicts to each other, and returns the differences.
        :param obj1: first dict
        :param obj2: second dict
        :param excluded_keys: keys that are ignored
        :return: true if match, false otherwise
        """
        keys = set(obj1._fields_ordered + obj2._fields_ordered)
        for key in keys:
            if key in excluded_keys:
                continue
            try:
                value1 = getattr(obj1, key)
                value2 = getattr(obj2, key)
                if type(value1) is BaseDict and type(value2) is BaseDict:
                    if not self._compare_basedicts(value1, value2):
                        return False
                else:
                    if value1 != value2:
                        return False
            except KeyError:
                return False
        return True

    def _compare_basedicts(self, obj1, obj2):
        keys = set(obj1.keys() + obj2.keys())
        for key in keys:
            try:
                value1 = obj1.get(key)
                value2 = obj2.get(key)
                if isnan(value1) and isnan(value2):
                    continue
                if value1 != value2:
                    return False
            except KeyError:
                return False
        return True
