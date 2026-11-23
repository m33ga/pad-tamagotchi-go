"""Render a private per-node config without shell interpolation of credentials."""
import os
from pathlib import Path

import yaml


def configuration(template: dict, env: dict[str, str]) -> dict:
    required = (
        'PATRONI_SCOPE', 'PATRONI_NAME', 'PATRONI_SUPERUSER_PASSWORD',
        'PATRONI_REPLICATION_PASSWORD', 'PATRONI_API_PASSWORD', 'POSTGRES_DB',
        'POSTGRES_USER', 'POSTGRES_PASSWORD', 'ANALYTICS_READER_PASSWORD',
        'POSTGRES_EXPORTER_PASSWORD',
    )
    for name in required:
        if not env.get(name):
            raise ValueError(f'{name} is required')
    if env['POSTGRES_USER'] in {'postgres', 'replicator', 'analytics_reader', 'monitoring'}:
        raise ValueError('POSTGRES_USER conflicts with an infrastructure role')
    config = template
    config['scope'], config['name'] = env['PATRONI_SCOPE'], env['PATRONI_NAME']
    config['restapi']['connect_address'] = env['PATRONI_NAME'] + ':8008'
    config['restapi']['authentication']['password'] = env['PATRONI_API_PASSWORD']
    pg = config['postgresql']
    pg['connect_address'] = env['PATRONI_NAME'] + ':5432'
    pg['data_dir'] = env.get('PGDATA', '/var/lib/postgresql/data/pgdata')
    pg['authentication']['superuser']['password'] = env['PATRONI_SUPERUSER_PASSWORD']
    pg['authentication']['replication']['password'] = env['PATRONI_REPLICATION_PASSWORD']
    parameters = config['bootstrap']['dcs']['postgresql']['parameters']
    parameters['max_prepared_transactions'] = 64 if config['scope'] in {'user-management', 'package-registry'} else 0
    # Used only in isolated tests; normal Compose always uses the three-member DCS.
    config['etcd3']['hosts'] = env.get('PATRONI_ETCD3_HOSTS', config['etcd3']['hosts'])
    return config


def main() -> None:
    with Path('/etc/patroni/patroni.yml').open() as source:
        config = configuration(yaml.safe_load(source), dict(os.environ))
    path = Path('/run/patroni/patroni.yml')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as target:
        yaml.safe_dump(config, target)
    os.execvp('patroni', ['patroni', str(path)])


if __name__ == '__main__':
    main()
