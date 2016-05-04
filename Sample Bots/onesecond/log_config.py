log_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s - %(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s',
        },
        'min': {
            'format': '%(levelname)-7s - [%(filename)s:%(funcName)s] %(message)s',
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
}
