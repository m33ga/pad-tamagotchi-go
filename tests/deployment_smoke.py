#!/usr/bin/env python3
"""Exercise the real Compose deployment with private disposable data and credentials."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import struct
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('user-management', 'battle', 'tamagotchi', 'notification',
            'map', 'monster-raid', 'guild', 'package-registry')


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def request(base, path, *, method='GET', body=None, token=None, content_type=None):
    headers = {'X-Correlation-ID': str(uuid.uuid4())}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            content_type = 'application/json'
        headers['Content-Type'] = content_type
    req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw.decode(errors='replace')
        return response.status, response.headers, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-pull', action='store_true', help='Use already pulled images.')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('auth_setup', ROOT / 'scripts/configure_services_auth.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    with tempfile.TemporaryDirectory(prefix='gateway-deployment-') as directory:
        temporary = Path(directory)
        project = 'gateway-deployment-' + secrets.token_hex(5)
        shutil.copyfile(ROOT / 'compose.yaml', temporary / 'compose.yaml')
        shutil.copytree(ROOT / 'config', temporary / 'config')
        env_text = (ROOT / '.env.example').read_text()
        gateway_port, chat_port = free_port(), free_port()
        # These values belong only to this disposable project.
        values = dict(line.split('=', 1) for line in env_text.splitlines()
                      if '=' in line and not line.startswith('#'))
        for name in values:
            if name.endswith('_PASSWORD'):
                values[name] = secrets.token_urlsafe(24)
            elif name.endswith('_DB_USER'):
                values[name] = 'deployment_test'
        values['GATEWAY_PORT'] = str(gateway_port)
        values['GUILD_CHAT_PORT'] = str(chat_port)
        values['GUILD_PUBLIC_WS_URL'] = f'ws://localhost:{chat_port}'
        (temporary / '.env').write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
        subprocess.run(['git', '-c', 'core.fsmonitor=false', 'init', '--quiet', str(temporary)], check=True)
        setup.ROOT = temporary
        setup.main()
        private_values = setup.read_env(temporary / '.env')
        command = ['docker', 'compose', '--project-name', project,
                   '--project-directory', str(temporary), '--env-file', str(temporary / '.env'),
                   '-f', str(temporary / 'compose.yaml')]
        # Do not inherit operator overrides or real credentials into the test.
        environment = os.environ.copy()
        for name in private_values:
            environment.pop(name, None)

        def compose(*arguments, check=True):
            return subprocess.run(command + list(arguments), check=check, capture_output=True,
                                  text=True, env=environment)

        def passed(name):
            print('PASS ' + name, flush=True)

        try:
            if not args.no_pull:
                print('Pulling the published deployment images...', flush=True)
                compose('pull')
            print('Starting the complete isolated stack...', flush=True)
            compose('up', '-d', '--wait', '--wait-timeout', '180', '--pull', 'never')
            passed('docker compose up -d --wait: all containers healthy')
            rendered = json.loads(compose('config', '--format', 'json').stdout)
            ids = compose('ps', '-q').stdout.split()
            containers = json.loads(subprocess.run(['docker', 'inspect', *ids], check=True,
                                                   capture_output=True, text=True).stdout)
            assert len(containers) == len(rendered['services'])
            for container in containers:
                name = container['Config']['Labels']['com.docker.compose.service']
                bindings = container['HostConfig'].get('PortBindings') or {}
                if name == 'api-gateway':
                    assert set(bindings) == {'8080/tcp'}
                elif name == 'guild-chat':
                    assert set(bindings) == {'8080/tcp'}
                else:
                    assert not bindings, name
                networks = set(container['NetworkSettings']['Networks'])
                assert networks == ({project + '_edge', project + '_internal'}
                                    if name in ('api-gateway', 'guild-chat') else {project + '_internal'}), name
                assert container['State']['Health']['Status'] == 'healthy', name
            network = json.loads(subprocess.run(['docker', 'network', 'inspect', project + '_internal'],
                                                check=True, capture_output=True, text=True).stdout)[0]
            assert network['Internal'] is True
            passed('only gateway HTTP and the separate Guild socket are published; internal isolation verified')
            base = f'http://127.0.0.1:{gateway_port}'
            status, _, _ = request(base, '/readyz')
            assert status == 200
            passed('gateway readiness includes successful JWKS discovery')
            status, _, body = request(base, '/')
            assert status == 404 and body['error']['code'] == 'ROUTE_NOT_FOUND'
            passed('unmatched root returns ROUTE_NOT_FOUND')
            for prefix in PREFIXES:
                status, _, body = request(base, '/' + prefix + '/api/v1/deployment-probe')
                assert status == 401 and body['error']['code'] == 'MISSING_TOKEN', (prefix, status)
            passed('every service prefix requires a token')
            status, _, body = request(base, '/user-management/.well-known/jwks.json')
            assert status == 200 and body['keys'][0]['kty'] == 'RSA'
            passed('public JWKS route strips the User Management prefix')
            # Seed one account only inside this disposable database. Identity V3
            # stores a PBKDF2 password hash; tokens still come from real UMS login.
            user_id, package_id = str(uuid.uuid4()), str(uuid.uuid4())
            password = secrets.token_urlsafe(24)
            salt = secrets.token_bytes(16)
            password_hash = base64.b64encode(
                b'\x01' + struct.pack('>III', 2, 100000, len(salt)) + salt
                + hashlib.pbkdf2_hmac('sha512', password.encode(), salt, 100000, dklen=32)
            ).decode()
            sql = ("INSERT INTO user_management.users "
                   '("Id", "Username", "NormalizedUsername", "Email", "NormalizedEmail", '
                   '"PasswordHash", "InitialPackageId", "CreatedAt") VALUES '
                   f"('{user_id}', 'deployment', 'DEPLOYMENT', 'deployment@example.test', "
                   f"'DEPLOYMENT@EXAMPLE.TEST', '{password_hash}', '{package_id}', NOW());")
            subprocess.run(command + ['exec', '-T', 'user-management-db', 'psql',
                                      '-U', 'deployment_test', '-d', 'user_management',
                                      '-v', 'ON_ERROR_STOP=1'], input=sql, check=True,
                           capture_output=True, text=True, env=environment)
            status, _, login = request(base, '/user-management/api/v1/auth/sessions',
                                       method='POST', body={'email': 'deployment@example.test',
                                                            'password': password})
            assert status == 200, ('UMS login', status)
            user_token = login['accessToken']
            status, _, profile = request(base, '/user-management/api/v1/users/' + user_id,
                                         token=user_token)
            assert status == 200 and profile['userId'] == user_id
            passed('public login issues a real user token accepted on a protected gateway route')
            path = '/user-management/api/v1/users/' + user_id + '/relationships'
            status, _, page = request(base, path + '?limit=1', token=user_token)
            assert status == 200 and page == {'items': [], 'nextCursor': None}
            status, _, _ = request(base, path + '?limit=0', token=user_token)
            assert status == 400
            passed('service prefix is stripped and query parameters reach the upstream unchanged')
            tokens = {}
            for client in setup.CLIENTS:
                prefix = client.removesuffix('-service').replace('-', '_').upper()
                form = urllib.parse.urlencode({'grant_type': 'client_credentials',
                                               'client_id': client,
                                               'client_secret': private_values[prefix + '_CLIENT_SECRET']}).encode()
                status, _, body = request(base, '/user-management/api/v1/oauth2/token', method='POST',
                                           body=form, content_type='application/x-www-form-urlencoded')
                assert status == 200 and body['token_type'] == 'Bearer', (client, status)
                tokens[client] = body['access_token']
            passed('all seven scoped client credentials obtain real issuer tokens through the gateway')
            for prefix in PREFIXES:
                if prefix == 'user-management':
                    path = '/.well-known/jwks.json'
                elif prefix in ('guild', 'package-registry'):
                    path = '/healthz'
                elif prefix in ('map', 'monster-raid'):
                    path = '/health'
                else:
                    path = '/_health'
                status, _, _ = request(base, '/' + prefix + path, token=tokens['guild-service'])
                assert status == 200, (prefix, status)
            passed('real upstream health responds through all eight prefixes with an issuer token')
            # On the public chat listener, REST must never be exposed.
            for path in ('/api/v1/guilds', '/healthz'):
                status, _, _ = request(f'http://127.0.0.1:{chat_port}', path)
                assert status == 404, ('chat listener exposes REST', path, status)
            status, _, _ = request(f'http://127.0.0.1:{chat_port}',
                                   '/ws/v1/guilds/' + str(uuid.uuid4()) + '/chat')
            assert status == 401, ('chat handshake must require a ticket', status)
            passed('Guild socket is reachable, requires a ticket, and exposes no REST routes')
            status, _, body = request(base, '/map/api/v1/users/' + str(uuid.uuid4()) + '/map',
                                       token='not-a-token')
            assert status == 401 and body['error']['code'] == 'INVALID_TOKEN'
            passed('gateway rejects malformed tokens before forwarding')
        except Exception as error:
            # App errors may include configuration. Redact every private generated value.
            logs = compose('logs', '--no-color', '--tail', '15', check=False).stdout
            message = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                message += '\n' + (error.stderr or '')
            for name, value in private_values.items():
                if value and ('PASSWORD' in name or 'SECRET' in name):
                    logs = logs.replace(value, '<redacted>')
                    message = message.replace(value, '<redacted>')
            print(message + '\n' + logs, flush=True)
            raise SystemExit(1) from error
        finally:
            compose('down', '--volumes', '--remove-orphans', check=False)


if __name__ == '__main__':
    main()
