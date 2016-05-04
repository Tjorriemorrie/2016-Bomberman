import logging
import pickle
import time
from copy import deepcopy
from itertools import product
from lib.treelib import Tree
from math import log, sqrt

logger = logging.getLogger(__name__)


class MonteCarlo:
    worlds = {}

    def __init__(self, world):
        '''
        Takes an instance of a Board and optionally some keyword
        arguments.  Initializes the list of game states and the
        statistics tables.

        Need to load the tree from disk or initiate it

        :param world: the world to run the simulations on
        '''
        self.worlds[world.id] = world
        self.tree = Tree()
        self.tree.create_node('root', world.id, data=[0, 0, 1])
        # self.tree.show()

    def best_action(self):
        '''
        Causes the AI to calculate the best move from the current game state and return it.
        Simulations are run for the alotted time.
        :return: int
        '''
        logger.info('start')

        # todo add deque of simulation time
        # todo add filter of max moves analyzed proportional from tree depth to max game moves against round #
        time_start = time.time()
        simulations = 0
        while time.time() < time_start + 2.:
            self.simulate()
            simulations += 1

        action = -1
        action_points = 0
        for child in self.tree.children(self.tree.root):
            logger.info('child {} {}'.format(child.tag, child.data))
            if child.data[2] >= 0 and child.data[0] > action_points:
                action_points = child.data[0]
                action = child.data[3]
        node_tree = self.tree[self.tree.root]
        logger.info('Final best move is {} with {}'.format(action, action_points))
        total_time = time.time() - time_start
        logger.error('Performance {} sims  at {:1f} [{}p in {:0f}s]'.format(
            simulations,
            node_tree.data[1] / total_time,
            node_tree.data[1],
            total_time,
        ))
        return action

    def simulate(self):
        '''
        Creates possible next states with all players actions. First
        states of hero moves, then all other opponents together.

        Repeat till no children and

        If no children then create all combinations of heros' moves.
        Pick best move.

        Next children will be combinations of all foes' moves.
        Pick worst combo.

        return (to update values and save).

        :return:
        '''
        logger.info('start')
        node = self.tree[self.tree.root]
        while not node.is_leaf():
            logger.info('node is not a leaf {}'.format(node.data))
            # hero moves
            logger.info([((child.data[0] / child.data[1]) + sqrt(log(node.data[1]) / child.data[1]), child) for child in self.tree.children(self.tree.root) if child.data[2] >= 0])
            val, hero_node = max([((child.data[0] / child.data[1]) + sqrt(log(node.data[1]) / child.data[1]), child) for child in self.tree.children(self.tree.root) if child.data[2] >= 0], key=lambda x: x[0])
            logger.info('val {}'.format(val))
            logger.info('child hero {}'.format(hero_node.tag))
            # foes moves
            logger.info([((child.data[0] / child.data[1]) + sqrt(log(hero_node.data[1]) / child.data[1]), child) for child in self.tree.children(hero_node.identifier) if child.data[2] >= 0])
            val, node = min([((child.data[0] / child.data[1]) + sqrt(log(hero_node.data[1]) / child.data[1]), child) for child in self.tree.children(hero_node.identifier) if child.data[2] >= 0], key=lambda x: x[0])
            logger.info('val {}'.format(val))
            logger.info('child combo {}'.format(node.tag))

        logger.info('|' * 50)
        logger.info('node {} [{}] is leaf: {}'.format(node.tag, node.identifier, node.data))

        world = deepcopy(self.worlds[node.identifier])
        world.tick()
        if world.status < 0:
            world.tock()
            self.propScore(world)

        logger.info('creating hero moves')
        for action_code, action_name in world.actions.items():
            world_hero = deepcopy(world)
            logger.info('*' * 40)
            logger.info('hero {} in {}'.format(action_name, world_hero.id))
            if not world_hero.take_action(action_code):
                logger.warn('{} is invalid for hero'.format(action_name))
                continue
            self.tree.create_node(action_name, world_hero.id, data=[0, 0, 1, action_code], parent=node.identifier)
            node_hero = self.tree[world_hero.id]
            logging.info('node hero {} [{}]: {} p={}'.format(node_hero.tag, node_hero.identifier, node_hero.data, node_hero.bpointer))
            # self.tree.show()
            # self.worlds[world_hero.id] = world_hero


            # get lists of legal foes actions
            foes = [f for f in world_hero.players if f != world_hero.hero]
            legals = [world_hero.legal_actions(f) for f in foes]
            logger.info(legals)

            # get combos of foes' actions
            for combo in product(*legals):
                logger.info('-' * 30)
                logger.info('combo {}'.format(combo))
                world_combo = deepcopy(world_hero)

                # take all foe actions
                for foe_action, foe_key in zip(combo, foes):
                    foe_action_name = world_combo.actions[foe_action]
                    logger.info('foe {} doing {}'.format(foe_key, foe_action_name))
                    world_combo.take_action(foe_action, foe_key)

                world_combo.tock()
                logger.info('world combo added to tree {}'.format(world_combo.id))
                self.tree.create_node(combo, world_combo.id, data=[0, 0, 1], parent=world_hero.id)
                node_combo = self.tree[world_combo.id]
                logging.info('combo node {}: {} p={}'.format(node_combo.tag, node_combo.data, node_combo.bpointer))
                self.tree.show()
                self.worlds[world_combo.id] = world_combo
                self.propScore(world_combo)

    def propScore(self, world):
        node = self.tree[world.id]
        data = [world.score, 1, world.status]
        node.data = data
        # logger.info('node = {}: {}'.format(node.tag, node.data))

        # update parents
        while node.bpointer:
            node = self.tree.parent(node.identifier)
            node.data[0] += data[0]
            node.data[1] += 1
            # logger.info('node = {}: {}'.format(node.tag, node.data))
