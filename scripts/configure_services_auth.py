#!/usr/bin/env python3
"""Configure private local service authentication without printing credentials."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = (
    'battle-service', 'monster-raid-service', 'map-service', 'guild-service',
    'tamagotchi-service', 'package-registry-service', 'notification-service',
)


def read_env(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


def private_write(path, content):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def main():
    tracked = subprocess.run(
        ['git', 'ls-files', '--', '.env', 'secrets/'], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout
    if tracked:
        raise SystemExit('Refusing configuration: private paths are tracked by Git.')
    private = ROOT / 'secrets'
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    env = ROOT / '.env'
    if not env.exists():
        private_write(env, (ROOT / '.env.example').read_text())
    backup = private / 'env-before-oauth.backup'
    if not backup.exists():
        private_write(backup, env.read_text())
    values = read_env(env)
    key = Path(values.get('JWT_PRIVATE_KEY_FILE', 'secrets/jwt-private.pem'))
    if not key.is_absolute():
        key = ROOT / key
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        subprocess.run([
            'openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
            'rsa_keygen_bits:2048', '-out', str(key),
        ], check=True, capture_output=True)
    # Rewrite the same bytes locally so Docker can read a cloud-offloaded host file.
    with tempfile.NamedTemporaryFile(dir=key.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(key.read_bytes())
    temporary.chmod(0o644)
    os.replace(temporary, key)
    # Only this file is bind-mounted; its private host directory blocks other users.
    for client in CLIENTS:
        path = private / (client + '.env')
        prefix = client.removesuffix('-service').replace('-', '_').upper()
        configured = values.get(prefix + '_CLIENT_SECRET', '')
        if configured and configured != 'change_me':
            secret = configured
        elif path.exists():
            secret = read_env(path)['OAUTH_CLIENT_SECRET']
        else:
            secret = secrets.token_urlsafe(32)
        token_url = values.get('GATEWAY_URL', 'http://api-gateway:8080').rstrip('/')
        private_write(path, f'OAUTH_CLIENT_ID={client}\nOAUTH_CLIENT_SECRET={secret}\n'
                      f'OAUTH_TOKEN_URL={token_url}/user-management/api/v1/oauth2/token\n')
        values[prefix + '_CLIENT_SECRET'] = secret
        values[prefix + '_CLIENT_SECRET_HASH'] = hashlib.sha256(secret.encode()).hexdigest()
    values.setdefault('JWT_KEY_ID', values.pop('USER_MANAGEMENT_JWT_KEY_ID', 'ums-key-1'))
    values.setdefault('JWT_PRIVATE_KEY_FILE', './secrets/jwt-private.pem')
    values.setdefault('GATEWAY_IMAGE', 'grdz/gateway:2.0.1')
    if values['GATEWAY_IMAGE'] == 'replace-with-published-gateway-image':
        values['GATEWAY_IMAGE'] = 'grdz/gateway:2.0.1'
    values.setdefault('JWT_PRIVATE_KEY_PATH', '/run/secrets/jwt-private.pem')
    values.setdefault('SERVICE_CLIENTS_PATH', '/app/config/service-clients.yaml')
    values.setdefault('GATEWAY_URL', 'http://api-gateway:8080')
    values.setdefault('REQUEST_TIMEOUT_SECONDS', values.pop('USER_MANAGEMENT_REQUEST_TIMEOUT_SECONDS', '10'))
    values.setdefault('MAX_CONCURRENCY', values.pop('USER_MANAGEMENT_MAX_CONCURRENCY', '64'))
    values.setdefault('USE_MOCK_PACKAGE_REGISTRY', 'false')
    values.setdefault('USE_MOCK_SERVICES', 'false')
    values.pop('JWT_SIGNING_KEY', None)
    values.pop('BATTLE_API_PORT', None)
    values.pop('GATEWAY_ISSUER_NETWORK', None)
    private_write(env, ''.join(f'{name}={value}\n' for name, value in values.items()))
    print('Configured private RSA key and seven clients; existing credentials preserved.')


if __name__ == '__main__':
    main()
