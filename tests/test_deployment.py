"""Check the rendered deployment and exported client collections for bypasses."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ('battle', 'monster-raid', 'map', 'guild', 'tamagotchi',
           'package-registry', 'notification')


def requests(items):
    for item in items:
        if 'item' in item:
            yield from requests(item['item'])
        elif 'request' in item:
            yield item


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Explicit placeholders prevent reading the operator's private local .env.
        env = os.environ.copy()
        for client in CLIENTS:
            prefix = client.replace('-', '_').upper()
            env[prefix + '_CLIENT_SECRET'] = 'fixture-' + client
            env[prefix + '_CLIENT_SECRET_HASH'] = hashlib.sha256(
                ('fixture-' + client).encode()).hexdigest()
        result = subprocess.run(
            ['docker', 'compose', '--env-file', str(ROOT / '.env.example'),
             '-f', str(ROOT / 'compose.yaml'), 'config', '--format', 'json'],
            check=True, capture_output=True, text=True, env=env,
        )
        cls.compose = json.loads(result.stdout)

    def test_only_gateway_and_guild_socket_publish_ports(self):
        services = self.compose['services']
        published = {name for name, service in services.items() if service.get('ports')}
        self.assertEqual(published, {'api-gateway', 'guild-chat'})
        self.assertEqual([port['target'] for port in services['api-gateway']['ports']], [8080])
        self.assertEqual([port['target'] for port in services['guild-chat']['ports']], [8080])

    def test_internal_network_and_no_api_on_edge(self):
        self.assertTrue(self.compose['networks']['internal']['internal'])
        for name, service in self.compose['services'].items():
            with self.subTest(service=name):
                expected = {'internal', 'edge'} if name in ('api-gateway', 'guild-chat') else {'internal'}
                self.assertEqual(set(service['networks']), expected)
                self.assertNotEqual(service.get('network_mode'), 'host')

    def test_readiness_and_issuer_startup_dependency(self):
        gateway = self.compose['services']['api-gateway']
        self.assertEqual(gateway['depends_on']['user-management-api']['condition'], 'service_healthy')
        self.assertIn('/readyz', ' '.join(gateway['healthcheck']['test']))
        self.assertNotIn('/healthz', ' '.join(gateway['healthcheck']['test']))

    def test_plaintext_credentials_are_scoped_to_their_client(self):
        services = self.compose['services']
        for client in CLIENTS:
            prefix = client.replace('-', '_').upper()
            for name, service in services.items():
                with self.subTest(client=client, service=name):
                    environment = service.get('environment', {})
                    values = list(environment.values())
                    if name == client + '-api':
                        self.assertIn('fixture-' + client, values)
                    else:
                        self.assertNotIn('fixture-' + client, values)
                    hash_name = prefix + '_CLIENT_SECRET_HASH'
                    self.assertEqual(hash_name in environment, name == 'user-management-api')
                    self.assertNotIn('env_file', service)
        mounts = services['api-gateway'].get('volumes', [])
        self.assertFalse(any('private' in mount['source'] for mount in mounts))
        self.assertTrue(any(mount['target'] == '/run/secrets/jwt-private.pem'
                            for mount in services['user-management-api']['volumes']))

    def test_collections_use_gateway_login_and_no_identity_spoofing(self):
        for path in (ROOT / 'collections').glob('*.postman_collection.json'):
            with self.subTest(collection=path.name):
                text = path.read_text()
                collection = json.loads(text)
                variables = {v['key']: v['value'] for v in collection['variable']}
                self.assertEqual(variables['gatewayUrl'], 'http://localhost:8000')
                urls = re.findall(r'https?://localhost:[0-9]+', text)
                self.assertEqual(set(urls), {'http://localhost:8000'})
                for obsolete in ('jwtSigningKey', 'CryptoJS', 'crypto-js', 'HS256'):
                    self.assertNotIn(obsolete, text)
                operations = list(requests(collection['item']))
                logins = [i for i in operations if i['request'].get('method') == 'POST'
                          and '/auth/sessions' in str(i['request']['url'])]
                self.assertTrue(logins)
                for operation in operations:
                    request = operation['request']
                    for header in request.get('header', []):
                        self.assertNotIn(header['key'].lower(), {
                            'x-user-id', 'x-user-role', 'x-session-id',
                            'x-caller-kind', 'x-service-name', 'x-scopes',
                        })
                    auth = request.get('auth', {})
                    if auth.get('type') == 'bearer':
                        self.assertNotIn('UserId', auth['bearer'][0]['value'])

    def test_gateway_submodule_uses_shared_github_url(self):
        result = subprocess.run(['git', 'config', '-f', str(ROOT / '.gitmodules'),
                                 '--get', 'submodule.gateway.url'],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'https://github.com/m33ga/gateway.git')
        recorded = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'ls-files',
                                   '--stage', 'gateway'], cwd=ROOT, check=True,
                                  capture_output=True, text=True).stdout
        self.assertTrue(recorded.startswith('160000 '), recorded)

    def test_secret_generator_format_and_entropy(self):
        generated = []
        for _ in range(2):
            result = subprocess.run(['python3', str(ROOT / 'scripts/generate_client_secret.py'),
                                     'battle-service'], check=True, capture_output=True, text=True)
            lines = dict(line.split('=', 1) for line in result.stdout.splitlines()
                         if not line.startswith('#'))
            secret = lines['BATTLE_CLIENT_SECRET']
            self.assertEqual(len(base64.urlsafe_b64decode(secret + '=')), 32)
            self.assertEqual(lines['BATTLE_CLIENT_SECRET_HASH'],
                             hashlib.sha256(secret.encode()).hexdigest())
            generated.append(secret)
        self.assertNotEqual(generated[0], generated[1])

    def test_setup_preserves_key_database_password_and_credentials(self):
        spec = importlib.util.spec_from_file_location('auth_setup', ROOT / 'scripts/configure_services_auth.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='gateway-auth-test-') as directory:
            temporary = Path(directory)
            shutil.copyfile(ROOT / '.env.example', temporary / '.env')
            subprocess.run(['git', '-c', 'core.fsmonitor=false', 'init', '--quiet', str(temporary)], check=True)
            module.ROOT = temporary
            module.main()
            values = module.read_env(temporary / '.env')
            key = (temporary / 'secrets/jwt-private.pem').read_bytes()
            module.main()
            self.assertEqual(key, (temporary / 'secrets/jwt-private.pem').read_bytes())
            self.assertEqual(values, module.read_env(temporary / '.env'))
            self.assertEqual(values['USER_MANAGEMENT_DB_PASSWORD'], 'change_me_to_a_strong_password')
            for client in CLIENTS:
                prefix = client.replace('-', '_').upper()
                secret = values[prefix + '_CLIENT_SECRET']
                self.assertEqual(values[prefix + '_CLIENT_SECRET_HASH'], hashlib.sha256(secret.encode()).hexdigest())
                self.assertEqual(secret, module.read_env(temporary / 'secrets' / (client + '-service.env'))['OAUTH_CLIENT_SECRET'])
            values['BATTLE_CLIENT_SECRET'] = 'rotated-local-fixture'
            (temporary / '.env').write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
            module.main()
            rotated = module.read_env(temporary / '.env')
            self.assertEqual(rotated['BATTLE_CLIENT_SECRET_HASH'],
                             hashlib.sha256(b'rotated-local-fixture').hexdigest())
            self.assertEqual(module.read_env(temporary / 'secrets/battle-service.env')['OAUTH_CLIENT_SECRET'],
                             'rotated-local-fixture')


if __name__ == '__main__':
    unittest.main()
