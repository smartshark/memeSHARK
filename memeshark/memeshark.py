import logging
import timeit
import sys
import copy

import networkx as nx
from mongoengine import connect, DoesNotExist
from dictdiffer import diff
from pycoshark.mongomodels import Project, VCSSystem, Commit, CodeEntityState, CodeGroupState
from pycoshark.utils import create_mongodb_uri_string

logger = logging.getLogger("main")


class MemeSHARK(object):
    """
    Implements the merging of code group states and code entity states to remove unchanged duplicates from the database.
    """

    progress_counter = 0
    no_commits = 0
    ces_total = 0
    ces_deleted_total = 0
    cg_total = 0
    cg_deleted_total = 0

    def __init__(self):
        pass

    def start(self, cfg):
        logger.setLevel(cfg.get_debug_level())
        start_time = timeit.default_timer()

        # Connect to mongodb
        uri = create_mongodb_uri_string(cfg.user, cfg.password, cfg.host, cfg.port, cfg.authentication_db,
                                        cfg.ssl_enabled)
        connect(cfg.database, host=uri)

        # Get the project for which issue data is collected
        try:
            project_id = Project.objects(name=cfg.project_name).get().id
        except DoesNotExist:
            logger.error('Project %s not found!' % cfg.project_name)
            sys.exit(1)

        # Get the VCS systems for the project
        vcs_systems = VCSSystem.objects(project_id=project_id).get().id
        logger.info("vcs_system_id: %s", vcs_systems)

        # Get the commits for the project
        self.no_commits = Commit.objects(vcs_system_id=vcs_systems).count()

        # Create commit graph
        commit_graph = self._generate_graph(vcs_systems)

        # find nodes without predecessor or with multiple predecessors
        for i, node in enumerate(commit_graph):
            if len(commit_graph.pred[node]) != 1:
                self._merge_path(commit_graph, node)

        logger.info("deleted %i of %i code entity states", self.ces_deleted_total, self.ces_total)
        logger.info("deleted %i of %i code group states", self.cg_deleted_total, self.cg_total)
        elapsed = timeit.default_timer() - start_time
        logger.info("Execution time: %0.5f s" % elapsed)

    def _merge_path(self, commit_graph, node):
        self.progress_counter += 1
        logger.info("start merging for path starting with node %s (%i / %i)", node, self.progress_counter, self.no_commits)
        # merges commits that are successors of this node

        ces_current_state = {}
        for ces in CodeEntityState.objects(commit_id=node):
            ces_current_state[ces.long_name] = ces

        #cg_current_state = {}
        #for cg in CodeGroupState.objects(commit_id=node):
        #    cg_current_state[cg.long_name] = cg

        self._add_ces_to_commit(node, ces_current_state)
        #self._add_cg_to_commit(node, cg_current_state)

        successor = commit_graph.succ[node];

        for i, succnode in enumerate(successor):
            #self._merge_node(commit_graph,succnode, ces_current_state, cg_current_state)
            self._merge_node(commit_graph, succnode, ces_current_state)


    #def _merge_node(self, commit_graph, node, ces_past_state, cg_past_state):
    def _merge_node(self, commit_graph, node, ces_past_state):
        if len(commit_graph.pred[node]) != 1:
            logger.info("node %s does not have exactly one parent. end of path.", node)
        else:
            self.progress_counter += 1
            logger.info("merging for node %s (%i / %i)", node, self.progress_counter, self.no_commits)
            ces_current_state = {} # contains CES that will be added to commit
            ces_map = {}           # for updating self-references
            ces_unchanged = []     # stores CES to be deleted

            #cg_current_state = {}  # contains CGs that will be added to commit
            #cg_map = {}            # for updating self-references
            #cg_unchanged = []      # stores cgs that will be deleted

            for ces in CodeEntityState.objects(commit_id=node):
                if ces.long_name not in ces_past_state:
                    ces_current_state[ces.long_name] = ces
                    ces_map[ces.id] = ces.id
                else:
                    ces_past = ces_past_state[ces.long_name]
                    old, new = self._compare_djangoobjects(ces_past, ces, {'id','s_key','commit_id','ce_parent_id','cg_ids'})
                    if len(new.keys())>0 or len(old.keys())>0:
                        ces_current_state[ces.long_name] = ces
                        ces_map[ces.id] = ces.id
                    else:
                        ces_current_state[ces.long_name] = ces_past
                        ces_map[ces.id] = ces_past.id
                        ces_unchanged.append(ces.id)

            updated_current_state = True
            while updated_current_state:
                updated_current_state = False
                for i,ces in ces_current_state.items():
                    if ces.ce_parent_id in ces_unchanged:
                        # do not delete currently referenced parents
                        ces_unchanged.remove(ces.ce_parent_id)
                        ces_parent = CodeEntityState.objects(id=ces.ce_parent_id).get()
                        ces_current_state[ces_parent.long_name] = ces_parent
                        updated_current_state = True
                        break

            # for cg in CodeGroupState.objects(commit_id=node):
            #     if cg.long_name not in cg_past_state:
            #         logger.info("new cg %s %s", cg.long_name, cg.id)
            #         cg_current_state[cg.long_name] = cg
            #         cg_map[cg.id] = cg.id
            #     else:
            #         cg_past = cg_past_state[cg.long_name]
            #         old, new = self._compare_djangoobjects(cg_past, cg, {'id', 's_key', 'commit_id', 'cg_parent_ids'})
            #         if len(new.keys())>0 or len(old.keys())>0:
            #             logger.info("keeping current cg: %s", cg.id)
            #             cg_current_state[cg.long_name] = cg
            #             cg_map[cg.id] = cg.id
            #         else:
            #             logger.info("replacing cg %s with past cg %s", cg.id, cg_past.id)
            #             cg_current_state[cg.long_name] = cg_past
            #             cg_map[cg.id] = cg_past.id
            #             cg_unchanged.append(cg.id)

            self._add_ces_to_commit(node, ces_current_state)
            #self._add_cg_to_commit(node, cg_current_state)
            #self._update_ces(node, ces_current_state, ces_unchanged, ces_map, cg_unchanged, cg_map)
            self._update_ces(node, ces_current_state, ces_unchanged, ces_map)
            #self._update_cg(node, cg_current_state, cg_unchanged, cg_map)
            self._delete_unchanged_ces(ces_unchanged, len(ces_current_state))
            #self._delete_unchanged_cg(cg_unchanged, len(cg_current_state))

            # recursively call for successors
            for i, succnode in enumerate(commit_graph.succ[node]):
                #self._merge_node(commit_graph, succnode, ces_current_state, cg_current_state)
                ces_state_argument = ces_current_state
                if len(commit_graph.succ[node])>1:
                    ces_state_argument = copy.deepcopy(ces_current_state)
                self._merge_node(commit_graph, succnode, ces_state_argument)

    def _add_ces_to_commit(self, node, current_state):
        commit = Commit.objects(id=node).get()
        ids = []
        for i, ces in current_state.items():
            ids.append(ces.id)
        commit.code_entity_states = ids
        commit.save()

    # def _add_cg_to_commit(self, node, current_state):
    #     commit = Commit.objects(id=node).get()
    #     ids = []
    #     for i, cg in current_state.items():
    #         ids.append(cg.id)
    #     commit.code_group_states = ids
    #     commit.save()

    #def _update_ces(self, node, ces_current_state, ces_unchanged, ces_map, cg_unchanged, cg_map):
    def _update_ces(self, node, ces_current_state, ces_unchanged, ces_map):
        for i, ces in ces_current_state.items():
            if ces.commit_id!=node:
                continue # skip CES from previous commits
            had_changes = False
            # updated CES references
            if ces.ce_parent_id in ces_unchanged:
                ces.ce_parent_id = ces_map[ces.ce_parent_id]
                had_changes = True

            # update CG references
            # cur_cg_ids = ces.cg_ids
            # for j, cg in enumerate(cur_cg_ids):
            #     if cg in cg_unchanged:
            #         cur_cg_ids[j] = cg_map[cg]
            #         had_changes = True
            # ces.cg_ids = cur_cg_ids

            if had_changes:
                ces.save()

    # def _update_cg(self, node, cg_current_state, cg_unchanged, cg_map):
    #     for i, cg in cg_current_state.items():
    #         if cg.commit_id!=node:
    #             continue # skip CG from previous commits
    #         had_changes = False
    #
    #         cur_parent_ids = cg.cg_parent_ids
    #         for j, cg_parent in enumerate(cur_parent_ids):
    #             if cg_parent in cg_unchanged:
    #                 cur_parent_ids[j] = cg_map[cur_parent_ids]
    #                 had_changes = True
    #         cg.cg_parent_ids = cur_parent_ids
    #
    #         if had_changes:
    #             cg.save()

    def _delete_unchanged_ces(self, ces_unchanged, no_ces):
        logger.info("deleting %i of %i code entity states", len(ces_unchanged), no_ces)
        self.ces_total += no_ces
        self.ces_deleted_total += len(ces_unchanged)
        for cesid in ces_unchanged:
            CodeEntityState.objects(id=cesid).delete()

    # def _delete_unchanged_cg(self, cg_unchanged, no_cg):
    #     logger.info("deleting %i of %i code group states", len(cg_unchanged), no_cg)
    #     self.cg_total += no_cg
    #     self.cg_deleted_total += len(cg_unchanged)
    #     for cgid in cg_unchanged:
    #         CodeGroupState.objects(id=cgid).delete()

    def _compare_djangoobjects(self, obj1, obj2, excluded_keys):
        keys = obj1._fields_ordered
        old, new = {}, {}
        for key in keys:
            if key in excluded_keys:
                continue
            try:
                value1 = getattr(obj1, key)
                value2 = getattr(obj2, key)
                if value1 != value2:
                    #if isinstance(value1, dict) and isinstance(value2, dict):
                    #    result = list(diff(value1, value2))
                    #    if len(result) > 0:
                    old.update({key: getattr(obj1, key)})
                    new.update({key: getattr(obj2, key)})
                    #else:
                    #    old.update({key: getattr(obj1, key)})
                    #    new.update({key: getattr(obj2, key)})
            except KeyError:
                old.update({key: getattr(obj1, key)})

        return old, new

    def _generate_graph(self, vcs_id):
        g = nx.DiGraph()
        # first we add all nodes to the graph
        for c in Commit.objects.timeout(False).filter(vcs_system_id=vcs_id):
            g.add_node(c.id)

        # after that we draw all edges
        for c in Commit.objects.timeout(False).filter(vcs_system_id=vcs_id):
            for p in c.parents:
                try:
                    p1 = Commit.objects.get(vcs_system_id=vcs_id, revision_hash=p)
                    g.add_edge(p1.id, c.id)
                except Commit.DoesNotExist:
                    logger.warning("parent of a commit is missing (commit id: %s - revision_hash: %s)", c.id, p)
                    pass
        return g