import argparse
import json
import logging
import logging.config
import os
import random
import sys

ACTIONS = {
    -1: 'DoNothing',
    1: 'MoveUp',
    2: 'MoveLeft',
    3: 'MoveRight',
    4: 'MoveDown',
    5: 'PlaceBomb',
    6: 'TriggerBomb',
}


def main(player_key, output_path):
    logger.info('Player key: {}'.format(player_key))
    logger.info('Output path: {}'.format(output_path))


    with open(os.path.join(output_path, 'state.json'), 'r', encoding='utf-8-sig') as f:
        state = json.load(f)

    action = random.choice(list(ACTIONS.keys()))
    logger.info('Action: {}'.format(ACTIONS[action]))

    with open(os.path.join(output_path, 'move.txt'), 'w') as f:
        f.write('{}\n'.format(action))


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('player_key', nargs='?')
    parser.add_argument('output_path', nargs='?', default=os.getcwd())
    args = parser.parse_args()

    assert (os.path.isdir(args.output_path))

    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'simple': {
                'format': '%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s',
            },
            'min': {
                'format': '%(levelname)-7s - [%(funcName)s] %(message)s',
            },
        },
        'filters': {},
        'handlers': {
            'stdout': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'min',
                'stream': 'ext://sys.stdout',
            },
            'stderr': {
                'level': 'ERROR',
                'class': 'logging.StreamHandler',
                'formatter': 'min',
                'stream': 'ext://sys.stderr',
            },
            'file': {
                'level': 'DEBUG',
                'class': 'logging.FileHandler',
                'formatter': 'min',
                'filename': 'p3.log',
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['stdout', 'stderr', 'file'],
        },
    })

    logger = logging.getLogger()
    sys.excepthook = handle_exception
    logger.disabled = False

    main(args.player_key, args.output_path)
