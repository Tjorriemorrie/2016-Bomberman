from copy import deepcopy
from itertools import product
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class World:
    width = 0
    height = 0
    map_bits = ''
    hero = None
    id = None
    state = {}
    visits = {}
    actions = {
        -1: 'DoNothing',
        1: 'MoveUp',
        2: 'MoveLeft',
        3: 'MoveRight',
        4: 'MoveDown',
        5: 'PlaceBomb',
        6: 'TriggerBomb',
    }
    players = {}
    dead = {}
    bombs = []
    explosions = []

    def __init__(self, state, hero, visits, extract=True):
        self.hero = hero
        self.id = str(uuid.uuid4())
        self.state = state
        self.visits = visits
        if extract:
            self.extract_meta()
        # todo player cannot move in direction if foe 2 spaces ahead (except hero)
        # todo keep separate history of where players moved for exploration points
        # todo trigger for multiple bombs set when first bomb already on 1?

    def __deepcopy__(self, memo):
        new = type(self)(deepcopy(self.state), self.hero, deepcopy(self.visits), False)
        new.width = self.width
        new.height = self.height
        new.map_bits = self.map_bits
        new.actions = deepcopy(self.actions)
        new.players = deepcopy(self.players)
        new.bombs = deepcopy(self.bombs)
        new.dead = deepcopy(self.dead)
        return new

    @property
    def status(self):
        state = 1
        if self.hero not in self.players:
            state = -1
        elif len(self.players) <= 1:
            state = 0
        # logger.info('game state = {}'.format(state))
        return state

    @property
    def score(self):
        min_points = min([p['Points'] for p in list(self.players.values()) + list(self.dead.values())])
        max_points = max([p['Points'] for p in list(self.players.values()) + list(self.dead.values())])
        points = self.players[self.hero]['Points'] if self.hero in self.players else self.dead[self.hero]['Points']
        # logger.info('points: {}'.format(points))
        try:
            hero_score = (points - min_points) / (max_points - min_points)
        except ZeroDivisionError:
            hero_score = 0.5
        # logger.info('Player score {:.3f}'.format(hero_score))
        return hero_score

    def extract_meta(self):
        '''
        Extract players info
        Extract bombs info
        Generate blocks bitmask
        :return:
        '''
        # dimensions
        self.width = self.state['MapWidth']
        self.height = self.state['MapHeight']
        logging.info('Map dimensions: {}x{} = {}'.format(self.width, self.height, self.width * self.height))

        # players
        for player in self.state['RegisteredPlayerEntities']:
            player['bit'] = (self.height - player['Location']['Y']) * self.width + (self.width - player['Location']['X'])
            self.players[player['Key']] = player
        logging.info('players extracted: {}'.format(self.players))

        # bombs and map bits
        for y in range(self.state['MapHeight']):
            for x in range(self.state['MapWidth']):
                b = '0'
                if self.state['GameBlocks'][x][y]['Bomb']:
                    bomb = self.state['GameBlocks'][x][y]['Bomb']
                    bomb['bit'] = (self.height - bomb['Location']['Y']) * self.width + (self.width - bomb['Location']['X'])
                    self.bombs.append(bomb)
                    b = '1'
                elif self.state['GameBlocks'][x][y]['Entity']:
                    b = '1'
                self.map_bits += b
                # logger.debug('{} for {}'.format(b, self.state['GameBlocks'][x][y]))
        logger.info('bombs extracted: {}'.format(self.bombs))
        logger.info('map bits extracted: [{}] {}'.format(len(str(self.map_bits)), self.map_bits))
        assert(len(str(self.map_bits)) == self.width * self.height)
        self.map_bits = int(self.map_bits, 2)
        logger.info('map bits [{}] {}'.format(type(self.map_bits), self.map_bits))

        # s = ''
        # for _, i in enumerate(bin(self.map_bits)[2:]):
        #     s += str(i)
        #     if len(s) == self.width:
        #         logger.info(s)
        #         s = ''

    def tick(self):
        '''
        Remove old explosions from the map
        Decrease all bomb timers
        Detonate bombs with a timer value of 0
        Trigger bombs that fall within the explosion range of another bomb
        Mark entities for destruction (Any players within a bomb blast at this moment will be killed)
        ...
        :return:
        '''
        logger.info('Game ticking round {}'.format(self.state['CurrentRound']))

        for bomb in self.bombs:
            bomb['BombTimer'] -= 1
            logger.info('decremented bomb {}'.format(bomb))
            if not bomb['BombTimer']:
                self.explode(bomb, bomb['Owner']['Key'])

        for key, player in self.players.items():
            px = player['Location']['X']
            py = player['Location']['Y']
            if self.state['GameBlocks'][px - 1][py - 1]['Exploding']:
                # do not assign points, tock will do that
                # hero can still die and should not get any points now
                logger.warn('Player {} killed!'.format(key))
                player['Killed'] = True
                self.dead[key] = player
                del self.players[key]

    def explode(self, bomb, player_key):
        '''
        Set isExploding flag to false (used when actioning trigger)
        Blast needs to propagate in each direction till it hits wall/bomb
        Does not stop hitting player
        :param bomb:
        :param player_key:
        :return:
        '''

        # todo the blast needs to travel till it hits an object

        bomb['IsExploding'] = True
        bx = bomb['Location']['X']
        by = bomb['Location']['Y']
        self.state['GameBlocks'][bx][by]['Bomb'] = bomb
        for loc in product(range(-bomb['BombRadius'], bomb['BombRadius'] + 1), repeat=2):
            logger.debug('block {} is exploding'.format(loc))
            try:
                self.state['GameBlocks'][bx - 1 + loc[0]][by + loc[1]]['Exploding'].append(player_key)
            except AttributeError:
                self.state['GameBlocks'][bx - 1 + loc[0]][by + loc[1]]['Exploding'] = [player_key]
            except IndexError:
                continue
            if self.state['GameBlocks'][bx - 1 + loc[0]][by + loc[1]]['Bomb']:
                bomb = next([b for b in self.bombs if b['Location']['X'] == bx - 1 + loc[0] + 1 and b['Location']['Y'] == by - 1 + loc[1] + 1])
                logger.info('Bomb chained at [{},{}]'.format(bx - 1 + loc[0], by - 1 + loc[1]))
                self.explode(bomb, player_key)

        # up
        for i in range(1, bomb['BombRadius']):
            block_up = (self.height - by + i) * self.width + (self.width - bx)
            # if not self.map_bits & 1 << block_up:

        logger.info('Bomb [{},{}] exploded by {}'.format(bx, by, player_key))

    def tock(self):
        '''
        ...
        Apply power ups
        Remove marked (Killed/Destroyed) entities from the map
        Apply player movement bonus
        :return:
        '''
        for player in self.players.values():
            block = self.state['GameBlocks'][player['Location']['X'] - 1][player['Location']['Y'] - 1]

            # powerups
            if block['PowerUp']:
                if any([bt in block['PowerUp']['$type'] for bt in ['Super', 'BombBag']]):
                    player['BombBag'] += 1
                    logger.info('Player {} bombag increased to {}'.format(player['Key'], player['BombBag']))
                if any([bt in block['PowerUp']['$type'] for bt in ['Super', 'BombRadius']]):
                    player['BombRadius'] *= 2
                    logger.info('Player {} bombradius increased to {}'.format(player['Key'], player['BombRadius']))
                if 'Super' in block['PowerUp']['$type'] and not block['Exploding']:
                    player['Points'] += 50
                    logger.info('Player {} got 50 points from bomb (has {})'.format(player['Key'], player['Points']))
                block['PowerUp'] = None
                logger.info('PowerUp consumed at [{},{}]'.format(block['Location']['X'], block['Location']['Y']))

            # killed
            if block['Exploding']:
                for bomb_player_key in set(block['Exploding']):
                    if bomb_player_key == player['Key']:
                        logger.warn('Player {} committed suicide!'.format(bomb_player_key))
                    else:
                        logger.warn('Player {} killed! {}'.format(bomb_player_key, player['Key']))
                        self.players[bomb_player_key]['Points'] += 250
                        logger.info('Player {} got 250 points (has {})'.format(bomb_player_key, self.players[bomb_player_key]['Points']))
                player['Killed'] = True
                player['Points'] -= 250
                logger.info('Player {} lost 250 points (has {})'.format(player['Key'], self.players[player['Key']]['Points']))
                self.dead[player['Key']] = player
                del self.players[player['Key']]

            # movement bonus
            else:
                loc = (player['Location']['X'], player['Location']['Y'])
                if loc not in self.visits[player['Key']]:
                    self.visits[player['Key']].add(loc)
                    player['Points'] += 1
                    # logger.info('Player {} movement 1 bonus (has {})'.format(player['Key'], player['Points']))

        # cleanup
        for row in self.state['GameBlocks']:
            for block in row:
                if block['Exploding']:
                    logger.debug('Block exploding {}'.format(block))
                    if '.Destruct' in block['Entity']['$type']:
                        for player_key in set(block['Exploding']):
                            try:
                                self.players[player_key]['Points'] += 10
                                logger.info('Player {} got 10 points for wall (has {})'.format(player_key, self.players[player_key]['Points']))
                            except IndexError:
                                logger.warn('Player {} died and cannot got 10 points for wall'.format(player_key))
                    block['Exploding'] = None
                    if not '.Indestruct' in block['Entity']['$type']:
                        block['Entity'] = None

        self.state['CurrentRound'] += 1

    def legal_actions(self, player_key=None):
        player_key = player_key or self.hero
        logger.debug('player_key: {}'.format(player_key))

        logger.info('calculating valid actions for player {}'.format(player_key))

        player_entity = self.players[player_key]
        logger.debug('player_entity: {}'.format(player_entity))

        px = player_entity['Location']['X']
        py = player_entity['Location']['Y']
        player_bombs = [b for b in self.bombs if b['Owner']['Key'] == player_key]
        logger.debug('player {} has {} bombs: {}'.format(player_key, len(player_bombs), player_bombs))

        # do nothing
        legal = [-1]
        legal_bit = [-1]

        # todo hero cannot move into exploding block

        # move up
        block_up = self.state['GameBlocks'][px - 1][py - 2]
        if not block_up['Entity'] and not block_up['Bomb']:
            legal.append(1)
        logger.info('width {}'.format(self.width))
        logger.info('height {}'.format(self.height))
        logger.info('px {}'.format(px))
        logger.info('py {}'.format(py))
        block_up = (self.height - py + 1) * self.width + (self.width - px)
        logger.info('bit block up {}'.format(block_up))
        if not self.map_bits & 1 << block_up:
            legal_bit.append(1)

        # move left
        block_left = self.state['GameBlocks'][px - 2][py - 1]
        if not block_left['Entity'] and not block_left['Bomb']:
            legal.append(2)
        block_left = (self.height - py) * self.width + (self.width - px + 1)
        logger.info('bit block left {}'.format(block_left))
        if not self.map_bits & 1 << block_left:
            legal_bit.append(2)

        # move right
        block_right = self.state['GameBlocks'][px + 0][py - 1]
        if not block_right['Entity'] and not block_right['Bomb']:
            legal.append(3)
        block_right = (self.height - py) * self.width + (self.width - px - 1)
        logger.info('bit block right {}'.format(block_right))
        if not self.map_bits & 1 << block_right:
            legal_bit.append(3)

        # move down
        block_down = self.state['GameBlocks'][px - 1][py + 0]
        # logger.debug('block down {}'.format(block_down))
        if not block_down['Entity'] and not block_down['Bomb']:
            legal.append(4)
        block_down = (self.height - py - 1) * self.width + (self.width - px)
        # logger.debug('bit block down {}'.format(block_down))
        logger.info(bin(self.map_bits)[-block_down])
        if not self.map_bits & 1 << block_down:
            legal_bit.append(4)

        # place bomb
        block_current = self.state['GameBlocks'][px - 1][py - 1]
        if not block_current['Bomb'] and len(player_bombs) < player_entity['BombBag']:
            legal.append(5)
        block_current = (self.height - py) * self.width + (self.width - px)
        logger.info('bit block current {}'.format(block_current))
        if not [b for b in player_bombs if b['bit'] == block_current] and len(player_bombs) < player_entity['BombBag']:
            legal_bit.append(5)

        # trigger bomb
        if len(player_bombs) > 0:
            legal.append(6)
            legal_bit.append(6)

        logger.info('Player {} has legal actions {}'.format(player_key, legal))
        logger.info('Player {} has legal bit actions {}'.format(player_key, legal_bit))
        assert(legal == legal_bit)
        return legal

    def take_action(self, action, player_key=None):
        '''
        ...
        Process player commands
        Mark entities for destruction (If a player moved into a bomb blast, they will be killed)
        ...
        :param action:
        :param player_key:
        :return:
        '''
        # todo action key is checked in logging at end
        if action not in self.actions:
            raise ValueError('Unknown action received {}'.format(action))

        player_key = player_key or self.hero
        logger.info('player {} taking action: {}'.format(player_key, action))

        player_entity = self.players[player_key]
        logger.debug('player_entity: {}'.format(player_entity))
        px = player_entity['Location']['X']
        py = player_entity['Location']['Y']
        player_bombs = [b for b in self.bombs if b['Owner']['Key'] == player_key]
        logger.debug('player {} has {} bombs: {}'.format(player_key, len(player_bombs), player_bombs))

        # do nothing
        if action == -1:
            pass

        # move up
        if action == 1:
            self.players[player_key]['Location']['Y'] -= 1
            self.state['GameBlocks'][px - 1][py - 2]['Entity'] = self.players[player_key]
            block_up = (self.height - py + 1) * self.width + (self.width - px)
            player_entity['bit'] = block_up
            # map = bin(self.map_bits)[2:]
            # map = map[::-1]
            # logger.warn('bit before {}'.format(map[block_up]))
            self.map_bits ^= 1 << block_up
            # map = bin(self.map_bits)[2:]
            # map = map[::-1]
            # logger.warn('bit after {}'.format(map[block_up]))

        # move left
        if action == 2:
            self.players[player_key]['Location']['X'] -= 1
            self.state['GameBlocks'][px - 2][py - 1]['Entity'] = self.players[player_key]
            block_left = (self.height - py) * self.width + (self.width - px + 1)
            player_entity['bit'] = block_left
            self.map_bits ^= 1 << block_left

        # move right
        if action == 3:
            self.players[player_key]['Location']['X'] += 1
            self.state['GameBlocks'][px - 0][py - 1]['Entity'] = self.players[player_key]
            block_right = (self.height - py) * self.width + (self.width - px - 1)
            player_entity['bit'] = block_right
            self.map_bits ^= 1 << block_right

        # move down
        if action == 4:
            self.players[player_key]['Location']['Y'] += 1
            self.state['GameBlocks'][px - 1][py - 0]['Entity'] = self.players[player_key]
            block_up = (self.height - py - 1) * self.width + (self.width - px)
            player_entity['bit'] = block_up
            self.map_bits ^= 1 << block_up

        if action in range(1, 5):
            self.state['GameBlocks'][px - 1][py - 1]['Entity'] = None
            block_current = (self.height - py) * self.width + (self.width - px)
            # block should only be flipped if player did not drop bomb
            if not any([b for b in player_bombs if b['bit'] == block_current]):
                self.map_bits ^= 1 << block_current

        # todo calc player block outside as it is reused

        # place bomb
        if action == 5:
            bomb = {
                "Owner": player_entity,
                "BombRadius": player_entity['BombRadius'],
                "BombTimer": min(10, player_entity['BombBag'] * 3 + 1),
                "IsExploding": False,
                "Location": player_entity['Location'],
                "bit": player_entity['bit'],
            }
            self.bombs.append(bomb)
            self.state['GameBlocks'][px - 1][py - 1]['Bomb'] = bomb
            # there will be an entity on the square already, no need to set

        # trigger bomb
        if action == 6:
            # todo bomb with timer 2+ ?
            oldest_bomb = min(player_bombs, key=lambda b: b['BombTimer'])
            # logger.debug('oldest bomb: {}'.format(oldest_bomb))
            bx = oldest_bomb['Location']['X'] - 1
            by = oldest_bomb['Location']['Y'] - 1
            oldest_bomb['BombTimer'] = 1
            self.state['GameBlocks'][bx][by]['Bomb'] = oldest_bomb
            # logger.debug('gameblocks {}'.format(self.state['GameBlocks'][bx - 1][by - 1]['Bomb']['BombTimer']))

        logger.info('Action {} taken for {}'.format(self.actions[action], player_key))
