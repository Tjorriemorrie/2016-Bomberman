import argparse
import json
import logging
import os
import pickle
import sys
from monte_carlo import MonteCarlo
from world import World

logger = logging.getLogger(__name__)
logger.disabled = False


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception


def main(player_key, output_path):
    logger.debug('Player key: {}'.format(player_key))
    logger.debug('Output path: {}'.format(output_path))

    # state
    with open(os.path.join(output_path, 'state.json'), 'r') as f:
        state = json.load(f)

    # visits
    try:
        with open(os.path.join(output_path, 'visits.pkl'), 'rb') as f:
            visits = pickle.load(f)
    except (EOFError, FileNotFoundError):
        visits = {}
    if state['CurrentRound'] == 1:
        visits = {}
    for player in state['RegisteredPlayerEntities']:
        try:
            visits[player['Key']].add((player['Location']['X'], player['Location']['Y']))
        except KeyError:
            visits[player['Key']] = {(player['Location']['X'], player['Location']['Y'])}
    with open(os.path.join(output_path, 'visits.pkl'), 'wb+') as f:
        pickle.dump(visits, f)
    logger.info('visits: {}'.format(visits))

    world = World(state, player_key, visits)
    monte_carlo = MonteCarlo(world)
    action = monte_carlo.best_action()

    # 20160429 1p in 108s
    # 20160503 108p in 2.6s
    # calculating legal moves upfront for hero and foes
    # 20160504 108p in 2.2s
    

    with open(os.path.join(output_path, 'move.txt'), 'w') as f:
        f.write('{}\n'.format(action))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('player_key', nargs='?')
    parser.add_argument('output_path', nargs='?', default=os.getcwd())
    args = parser.parse_args()

    assert (os.path.isdir(args.output_path))

    import logging.config
    from log_config import log_config
    logging.config.dictConfig(log_config)

    main(args.player_key, args.output_path)
