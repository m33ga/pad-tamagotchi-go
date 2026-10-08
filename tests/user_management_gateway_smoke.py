"""Isolated real gateway + UMS + PostgreSQL test; Package Registry is an HTTP fixture.

Build the two local images first, then run this script. No real .env or credentials
are consumed; its disposable Compose project and database volume are removed.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ('battle-service', 'monster-raid-service', 'map-service', 'guild-service',
           'tamagotchi-service', 'package-registry-service', 'notification-service')
PACKAGE = '11111111-1111-4111-8111-111111111111'
FIXTURE = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
records = []
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args): pass
    def handle_request(self):
        if self.path == '/observed':
            status, body = 200, records
        else:
            if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                chunks = []
                while True:
                    size = int(self.rfile.readline().split(b';')[0], 16)
                    if not size:
                        while self.rfile.readline() != b'\r\n': pass
                        break
                    chunks.append(self.rfile.read(size)); self.rfile.read(2)
                raw = b''.join(chunks)
            else:
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            body = json.loads(raw) if raw else None
            identity = self.headers.get('X-Service-Name')
            records.append({'method': self.command, 'path': self.path,
                'service': identity, 'kind': self.headers.get('X-Caller-Kind'),
                'correlation': self.headers.get('X-Correlation-ID'),
                'authorization_present': 'Authorization' in self.headers,
                'body': body})
            if identity != 'user-management-service':
                status, body = 403, {'error': {'code': 'FORBIDDEN'}}
            elif self.command == 'GET':
                status, body = 200, {'status': 'ACTIVE'}
            else:
                status, body = 201, {'registered': True}
        payload = json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload))); self.end_headers()
        self.wfile.write(payload)
    do_GET = handle_request
    do_POST = handle_request
ThreadingHTTPServer(('0.0.0.0', 8082), Handler).serve_forever()
'''


def docker(*args, **kwargs):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, **kwargs)
    if result.returncode:
        # Environment and container diagnostics may include private values.
        detail = result.stderr
        for name, value in kwargs.get('env', {}).items():
            if value and ('SECRET' in name or 'PASSWORD' in name): detail = detail.replace(value, '<redacted>')
        raise RuntimeError('Docker operation failed: ' + args[0] + '\n' + detail[-1500:])
    return result.stdout.strip()


def claims(token):
    encoded = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))


class IntegrationTests(unittest.TestCase):
    base = None
    client_secrets = {}
    fixture = None
    api = None

    def request(self, method, path, body=None, token=None, headers=None, form=False):
        combined = dict(headers or {})
        if token: combined['Authorization'] = 'Bearer ' + token
        if body is not None:
            combined['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
            body = (urlencode(body) if form else json.dumps(body)).encode()
        req = Request(self.base + path, data=body, method=method, headers=combined)
        try: response = urlopen(req, timeout=20)
        except HTTPError as error: response = error
        with response:
            content = response.read()
            return response.status, json.loads(content) if content else None, response.headers

    def service_token(self, client, scope=None):
        body = {'grant_type': 'client_credentials', 'client_id': client,
                'client_secret': self.client_secrets[client]}
        if scope is not None: body['scope'] = scope
        status, response, headers = self.request('POST', '/user-management/api/v1/oauth2/token', body, form=True)
        self.assertEqual(200, status)
        self.assertEqual('no-store', headers['Cache-Control'])
        self.assertEqual(300, response['expires_in'])
        self.assertEqual(client, claims(response['access_token'])['sub'])
        return response['access_token']

    def account(self):
        suffix = uuid.uuid4().hex[:20]
        credentials = {'email': suffix + '@example.com', 'password': 'ExamplePass123!'}
        status, user, headers = self.request('POST', '/user-management/api/v1/users',
            credentials | {'username': suffix, 'initialPackageId': PACKAGE},
            headers={'X-Correlation-ID': 'integration-' + suffix, 'Authorization': 'Bearer ignored',
                     'X-Caller-Kind': 'service', 'X-Service-Name': 'spoofed'})
        self.assertEqual(201, status, user.get('error', {}).get('code'))
        status, session, _ = self.request('POST', '/user-management/api/v1/auth/sessions', credentials)
        self.assertEqual(200, status)
        return user, session, headers['X-Correlation-ID']

    def test_public_jwks_and_all_seven_client_tokens(self):
        status, document, headers = self.request('GET', '/user-management/.well-known/jwks.json')
        self.assertEqual(200, status)
        self.assertEqual('public, max-age=300', headers['Cache-Control'])
        self.assertEqual('RS256', document['keys'][0]['alg'])
        self.assertNotIn('d', document['keys'][0])
        for client in CLIENTS:
            token = self.service_token(client)
            payload = claims(token)
            self.assertEqual('service', payload['kind'])
            self.assertEqual('tamagotchi-go', payload['iss'])
            self.assertEqual(300, payload['exp'] - payload['iat'])
            self.assertIn('jti', payload)

    def test_oauth_standard_errors_through_public_route(self):
        valid = {'client_id': 'battle-service', 'client_secret': self.client_secrets['battle-service']}
        for body, expected, code in [
            (valid, 400, 'invalid_request'),
            (valid | {'grant_type': 'password'}, 400, 'unsupported_grant_type'),
            (valid | {'grant_type': 'client_credentials', 'scope': 'forbidden:write'}, 400, 'invalid_scope'),
            (valid | {'grant_type': 'client_credentials', 'client_secret': 'wrong'}, 401, 'invalid_client'),
        ]:
            status, response, headers = self.request('POST', '/user-management/api/v1/oauth2/token', body, form=True)
            self.assertEqual(expected, status); self.assertEqual(code, response['error'])
            if status == 401: self.assertEqual('Basic realm="tamagotchi-go"', headers['WWW-Authenticate'])

    def test_verified_user_identity_owner_checks_and_logout(self):
        user, session, _ = self.account(); other, other_session, _ = self.account()
        path = '/user-management/api/v1/users/' + user['userId']
        token = session['accessToken']
        self.assertEqual(user['userId'], claims(token)['sub']); self.assertIn('sid', claims(token))
        self.assertEqual(200, self.request('GET', path, token=token)[0])
        self.assertEqual(403, self.request('GET', path, token=other_session['accessToken'],
            headers={'X-User-ID': user['userId'], 'X-Caller-Kind': 'user'})[0])
        status, response, _ = self.request('GET', path, headers={'X-User-ID': user['userId'], 'X-Caller-Kind': 'user'})
        self.assertEqual(401, status); self.assertEqual('MISSING_TOKEN', response['error']['code'])
        status, response, _ = self.request('GET', path, token='malformed')
        self.assertEqual(401, status); self.assertEqual('INVALID_TOKEN', response['error']['code'])
        self.assertEqual(204, self.request('DELETE', '/user-management/api/v1/auth/sessions/current', token=token)[0])
        status, response, _ = self.request('POST', '/user-management/api/v1/auth/session-refreshes',
                                         {'refreshToken': session['refreshToken']})
        self.assertEqual(401, status); self.assertEqual('INVALID_REFRESH_TOKEN', response['error']['code'])
        # Logout revokes refresh, while the stateless access token expires normally.
        self.assertEqual(200, self.request('GET', path, token=token)[0])

    def test_service_balances_allow_only_battle_and_monster_raid(self):
        user, session, _ = self.account(); path = '/user-management/api/v1/users/' + user['userId'] + '/balances'
        def credit(token, headers=None):
            return self.request('POST', path, {'currency': 'GLOBAL', 'amount': 5, 'reason': 'BATTLE_REWARD',
                'referenceId': str(uuid.uuid4())}, token=token,
                headers={'Idempotency-Key': str(uuid.uuid4())} | (headers or {}))[0]
        self.assertEqual(403, credit(session['accessToken'], {'X-Service-Name': 'battle-service', 'X-Caller-Kind': 'service'}))
        self.assertEqual(403, credit(self.service_token('map-service'), {'X-Service-Name': 'battle-service'}))
        self.assertEqual(200, credit(self.service_token('battle-service')))
        self.assertEqual(200, credit(self.service_token('monster-raid-service')))
        status, balance, _ = self.request('GET', path, token=session['accessToken'])
        self.assertEqual(200, status); self.assertEqual(10, balance['globalBalance'])

    def test_outbound_uses_real_gateway_and_preserves_correlation(self):
        user, _, correlation = self.account()
        records = json.loads(docker('exec', self.fixture, 'python', '-c',
            "import urllib.request; print(urllib.request.urlopen('http://localhost:8082/observed').read().decode())"))
        matching = [r for r in records if r['correlation'] == correlation]
        self.assertEqual(['GET', 'POST'], [r['method'] for r in matching])
        for record in matching:
            self.assertEqual('service', record['kind'])
            self.assertEqual('user-management-service', record['service'])
            self.assertFalse(record['authorization_present'])
        self.assertEqual({'userId': user['userId']}, matching[1]['body'])

    def test_unsigned_and_symmetric_tokens_are_rejected(self):
        import hmac
        user, session, _ = self.account()
        path = '/user-management/api/v1/users/' + user['userId']
        payload = session['accessToken'].split('.')[1]
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
        for algorithm in ('none', 'HS256'):
            header = encode(json.dumps({'alg': algorithm, 'kid': 'ums-lab2-1'}).encode())
            signing_input = (header + '.' + payload).encode()
            signature = encode(hmac.new(secrets.token_bytes(32), signing_input, hashlib.sha256).digest()) if algorithm == 'HS256' else ''
            status, response, _ = self.request('GET', path, token=header + '.' + payload + '.' + signature)
            self.assertEqual(401, status); self.assertEqual('INVALID_TOKEN', response['error']['code'])

    def test_no_ums_host_port_and_missing_direct_identity_rejected(self):
        ports = json.loads(docker('inspect', '--format', '{{json .HostConfig.PortBindings}}', self.api))
        self.assertFalse(ports)
        status = docker('exec', self.api, 'curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                        'http://localhost:8080/api/v1/users/' + str(uuid.uuid4()))
        self.assertEqual('401', status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway-image', default='grdz/gateway:dev')
    parser.add_argument('--ums-image', default='sanda2004/user-management-service:2.0.0')
    args = parser.parse_args()
    project = 'ums-gateway-test-' + uuid.uuid4().hex[:10]
    fixture = project + '-package-fixture'
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory); temp.chmod(0o755)
        key = temp / 'key.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                        '-out', str(key)], check=True, capture_output=True); key.chmod(0o644)
        env = {k: v for k, v in os.environ.items() if not k.endswith('_CLIENT_SECRET_HASH')}
        values = dict(line.split('=', 1) for line in (ROOT / '.env.example').read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
        values.update({'USER_MANAGEMENT_DB_NAME': 'issuer_test', 'USER_MANAGEMENT_DB_USER': 'issuer_test',
                  'USER_MANAGEMENT_DB_PASSWORD': secrets.token_urlsafe(32), 'GATEWAY_IMAGE': args.gateway_image,
                  'GATEWAY_ISSUER_NETWORK': project + '-issuer'})
        for client in CLIENTS:
            secret = secrets.token_urlsafe(32); IntegrationTests.client_secrets[client] = secret
            values[client.removesuffix('-service').replace('-', '_').upper() + '_CLIENT_SECRET_HASH'] = hashlib.sha256(secret.encode()).hexdigest()
        env.update(values)
        envfile = temp / '.env'; envfile.write_text(''.join(f'{k}={v}\n' for k,v in values.items())); envfile.chmod(0o600)
        override = temp / 'override.yaml'
        override.write_text(f'''services:
  user-management-api:
    image: {args.ums_image}
    pull_policy: never
    volumes:
      - {key}:/run/secrets/jwt-private.pem:ro
  api-gateway:
    pull_policy: never
    ports: !override ["127.0.0.1:0:8080"]
''')
        command = ['compose', '-p', project, '--project-directory', str(ROOT), '--env-file', str(envfile),
                   '-f', str(ROOT/'compose.yaml'), '-f', str(ROOT/'compose.gateway.yaml'), '-f', str(override)]
        try:
            docker(*command, 'up', '-d', '--wait', 'user-management-api', 'api-gateway', env=env)
            fixture_file = temp / 'fixture.py'; fixture_file.write_text(FIXTURE); fixture_file.chmod(0o644)
            docker('run', '-d', '--name', fixture, '--network', project + '_default',
                   '--network-alias', 'package-registry-api', '-v', f'{fixture_file}:/fixture.py:ro',
                   '--entrypoint', 'python', args.gateway_image, '/fixture.py')
            for attempt in range(60):
                try:
                    docker('exec', fixture, 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8082/observed')")
                    break
                except RuntimeError: time.sleep(0.1)
            else: raise RuntimeError('Package fixture did not become ready.')
            api = docker(*command, 'ps', '-q', 'user-management-api', env=env)
            gateway = docker(*command, 'ps', '-q', 'api-gateway', env=env)
            address = docker('port', gateway, '8080/tcp').splitlines()[0]
            IntegrationTests.base = 'http://' + address; IntegrationTests.fixture = fixture; IntegrationTests.api = api
            for attempt in range(60):
                try:
                    with urlopen(IntegrationTests.base + '/readyz', timeout=2) as response:
                        if response.status == 200: break
                except (URLError, HTTPError): time.sleep(0.25)
            else: raise RuntimeError('Gateway did not become ready.')
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests))
            for service in ('api-gateway', 'user-management-api'):
                logs = docker(*command, 'logs', '--no-color', service, env=env)
                assert not any(secret in logs for secret in IntegrationTests.client_secrets.values()), 'Secret appeared in logs'
            if not result.wasSuccessful():
                records = docker('exec', fixture, 'python', '-c', "import urllib.request; print(urllib.request.urlopen('http://localhost:8082/observed').read().decode())")
                print('Fixture observations:', records)
                logs = docker(*command, 'logs', '--no-color', 'api-gateway', env=env)
                print('Gateway request events:', '\n'.join(line for line in logs.splitlines() if 'request completed' in line)[-5000:])
                raise SystemExit(1)
        finally:
            subprocess.run(['docker', 'rm', '-f', fixture], capture_output=True)
            subprocess.run(['docker', *command, 'down', '-v'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
