"""Deployment rules that must not silently diverge from the database contract."""
import copy
import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure', ROOT / 'configure.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.template = yaml.safe_load((ROOT / 'patroni.yml').read_text())
        self.env = {name: 'test-only' for name in (
            'PATRONI_SUPERUSER_PASSWORD', 'PATRONI_REPLICATION_PASSWORD',
            'PATRONI_API_PASSWORD', 'POSTGRES_PASSWORD',
            'ANALYTICS_READER_PASSWORD', 'POSTGRES_EXPORTER_PASSWORD',
        )}
        self.env.update(PATRONI_SCOPE='guild', PATRONI_NAME='guild-db-1', POSTGRES_USER='guild_app', POSTGRES_DB='guild')

    def render(self):
        return module.configuration(copy.deepcopy(self.template), self.env)

    def test_prepared_transactions_only_for_participants(self):
        for cluster in ('guild', 'broker', 'battle', 'tamagotchi', 'notification', 'monster-raid', 'user-management', 'package-registry'):
            with self.subTest(cluster=cluster):
                self.env['PATRONI_SCOPE'] = cluster
                value = self.render()['bootstrap']['dcs']['postgresql']['parameters']['max_prepared_transactions']
                self.assertEqual(value, 64 if cluster in {'user-management', 'package-registry'} else 0)

    def test_credentials_with_yaml_characters_round_trip_as_strings(self):
        secret = 'a: b # c\n"quoted" $HOME'
        self.env['PATRONI_SUPERUSER_PASSWORD'] = secret
        config = yaml.safe_load(yaml.safe_dump(self.render()))
        self.assertEqual(config['postgresql']['authentication']['superuser']['password'], secret)

    def test_missing_secret_and_reserved_role_are_rejected(self):
        del self.env['ANALYTICS_READER_PASSWORD']
        with self.assertRaisesRegex(ValueError, 'ANALYTICS_READER_PASSWORD is required'):
            self.render()
        self.env['ANALYTICS_READER_PASSWORD'] = 'test-only'
        self.env['POSTGRES_USER'] = 'postgres'
        with self.assertRaisesRegex(ValueError, 'infrastructure role'):
            self.render()

    def test_timeouts_supported_by_real_patroni(self):
        from patroni.config import Config
        dcs = self.render()['bootstrap']['dcs']
        actual = Config('', validator=None)
        actual.set_dynamic_configuration(copy.deepcopy(dcs))
        self.assertEqual(actual['ttl'], 20)
        self.assertEqual(actual['loop_wait'], 2)
        self.assertEqual(actual['retry_timeout'], 5)
        self.assertLessEqual(actual['loop_wait'] + 2 * actual['retry_timeout'], actual['ttl'])

    def test_rewind_requires_checksums_and_is_enabled(self):
        config = self.render()
        self.assertIn('data-checksums', config['bootstrap']['initdb'])
        self.assertTrue(config['bootstrap']['dcs']['postgresql']['use_pg_rewind'])


if __name__ == '__main__':
    unittest.main()
