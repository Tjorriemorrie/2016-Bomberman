from copy import deepcopy
from itertools import product
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class World:
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
        # players
        for player in self.state['RegisteredPlayerEntities']:
            self.players[player['Key']] = player
        logging.info('players extracted: {}'.format(self.players))

        # bombs
        for x in range(self.state['MapWidth']):
            for y in range(self.state['MapHeight']):
                if self.state['GameBlocks'][x][y]['Bomb']:
                    self.bombs.append(self.state['GameBlocks'][x][y]['Bomb'])
        logger.info('bombs extracted: {}'.format(self.bombs))

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
            px = player['Location']['X'] - 1
            py = player['Location']['Y'] - 1
            if self.state['GameBlocks'][px][py]['Exploding']:
                # do not assign points, tock will do that
                # hero can still die and should not get any points now
                logger.warn('Player {} killed!'.format(key))
                player['Killed'] = True
                self.dead[key] = player
                del self.players[key]


    def explode(self, bomb, player_key):
        bomb['IsExploding'] = True
        bx = bomb['Location']['X'] - 1
        by = bomb['Location']['Y'] - 1
        self.state['GameBlocks'][bx][by]['Bomb'] = bomb
        for loc in product(range(-bomb['BombRadius'], bomb['BombRadius'] + 1), repeat=2):
            logger.debug('block {} is exploding'.format(loc))
            try:
                self.state['GameBlocks'][bx + loc[0]][by + loc[1]]['Exploding'].append(player_key)
            except AttributeError:
                self.state['GameBlocks'][bx + loc[0]][by + loc[1]]['Exploding'] = player_key
            except IndexError:
                continue
            if self.state['GameBlocks'][bx + loc[0]][by + loc[1]]['Bomb']:
                bomb = next([b for b in self.bombs if b['Location']['X'] == bx + loc[0] + 1 and b['Location']['Y'] == by + loc[1] + 1])
                logger.info('Bomb chained at [{},{}]'.format(bx + loc[0], by + loc[1]))
                self.explode(bomb, player_key)
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
                        logger.warn('Player {} killed {}!'.format(bomb_player_key, player['Key']))
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
        # logger.info('action: {}'.format(action))
        player_key = player_key or self.hero
        # logger.info('player_key: {}'.format(player_key))
        player_entity = self.players[player_key]
        # logger.debug('player_entity: {}'.format(player_entity))
        px = player_entity['Location']['X']
        py = player_entity['Location']['Y']
        player_bombs = [b for b in self.bombs if b['Owner']['Key'] == player_key]
        # logger.debug('player {} has {} bombs: {}'.format(player_key, len(player_bombs), player_bombs))

        # do nothing
        if action == -1:
            pass

        # movements
        elif action in range(1, 5):

            # todo hero cannot move into exploding block
            # todo foe cannot move 2nd block to hero

            # move up
            if action == 1:
                block = self.state['GameBlocks'][px - 1][py - 2]
                if block['Entity'] or block['Bomb']:
                    return False
                self.state['GameBlocks'][px - 1][py - 1]['Entity'] = None
                self.players[player_key]['Location']['Y'] -= 1
                self.state['GameBlocks'][px - 1][py - 2]['Entity'] = self.players[player_key]

            # move left
            if action == 2:
                block = self.state['GameBlocks'][px - 2][py - 1]
                if block['Entity'] or block['Bomb']:
                    return False
                self.state['GameBlocks'][px - 1][py - 1]['Entity'] = None
                self.players[player_key]['Location']['X'] -= 1
                self.state['GameBlocks'][px - 2][py - 1]['Entity'] = self.players[player_key]

            # move right
            elif action == 3:
                block = self.state['GameBlocks'][px - 0][py - 1]
                if block['Entity'] or block['Bomb']:
                    return False
                self.state['GameBlocks'][px - 1][py - 1]['Entity'] = None
                self.players[player_key]['Location']['X'] += 1
                self.state['GameBlocks'][px - 0][py - 1]['Entity'] = self.players[player_key]

            # move down
            elif action == 4:
                block = self.state['GameBlocks'][px - 1][py - 0]
                if block['Entity'] or block['Bomb']:
                    return False
                self.state['GameBlocks'][px - 1][py - 1]['Entity'] = None
                self.players[player_key]['Location']['Y'] += 1
                self.state['GameBlocks'][px - 1][py - 0]['Entity'] = self.players[player_key]

        # place bomb
        elif action == 5:
            if len(player_bombs) >= player_entity['BombBag']:
                return False
            if self.state['GameBlocks'][px - 1][py - 1]['Bomb']:
                return False
            bomb = {
                "Owner": player_entity,
                "BombRadius": player_entity['BombRadius'],
                "BombTimer": min(10, player_entity['BombBag'] * 3 + 1),
                "IsExploding": False,
                "Location": player_entity['Location'],
            }
            self.state['GameBlocks'][px - 1][py - 1]['Bomb'] = bomb
            self.bombs.append(bomb)

        # trigger bomb
        elif action == 6:
            if len(player_bombs) < 1:
                return False
            if any([b for b in player_bombs if b['IsExploding']]):
                return False
            oldest_bomb = min(player_bombs, key=lambda b: b['BombTimer'])
            # logger.debug('oldest bomb: {}'.format(oldest_bomb))
            bx = oldest_bomb['Location']['X'] - 1
            by = oldest_bomb['Location']['Y'] - 1
            oldest_bomb['BombTimer'] = 1
            self.state['GameBlocks'][bx][by]['Bomb'] = oldest_bomb
            # logger.debug('gameblocks {}'.format(self.state['GameBlocks'][bx - 1][by - 1]['Bomb']['BombTimer']))

        # 404
        else:
            raise ValueError('Unknown action received {}'.format(action))

        # logger.info('Action {} taken for {}'.format(self.actions[action], player_key))
        return True

