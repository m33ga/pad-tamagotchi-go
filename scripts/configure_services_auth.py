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
    key = private / 'jwt-private.pem'
    if not key.exists():
        subprocess.run([
            'openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
            'rsa_keygen_bits:2048', '-out', str(key),
        ], check=True, capture_output=True)
    # Rewrite the same bytes locally so Docker can read a cloud-offloaded host file.
    with tempfile.NamedTemporaryFile(dir=private, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(key.read_bytes())
    temporary.chmod(0o644)
    os.replace(temporary, key)
    # Only this file is bind-mounted; its private host directory blocks other users.
    for client in CLIENTS:
        path = private / (client + '.env')
        if not path.exists():
            secret = secrets.token_urlsafe(32)
            private_write(path, f'OAUTH_CLIENT_ID={client}\nOAUTH_CLIENT_SECRET={secret}\n'
                          'OAUTH_TOKEN_URL=http://api-gateway:8080/user-management/api/v1/oauth2/token\n')
        path.chmod(0o600)
        secret = read_env(path)['OAUTH_CLIENT_SECRET']
        prefix = client.removesuffix('-service').replace('-', '_').upper()
        values[prefix + '_CLIENT_SECRET_HASH'] = hashlib.sha256(secret.encode()).hexdigest()
    values.setdefault('JWT_KEY_ID', values.pop('USER_MANAGEMENT_JWT_KEY_ID', 'ums-key-1'))
    values.setdefault('JWT_PRIVATE_KEY_PATH', '/run/secrets/jwt-private.pem')
    values.setdefault('SERVICE_CLIENTS_PATH', '/app/config/service-clients.yaml')
    values.setdefault('GATEWAY_URL', 'http://api-gateway:8080')
    values.setdefault('REQUEST_TIMEOUT_SECONDS', values.pop('USER_MANAGEMENT_REQUEST_TIMEOUT_SECONDS', '10'))
    values.setdefault('MAX_CONCURRENCY', values.pop('USER_MANAGEMENT_MAX_CONCURRENCY', '64'))
    values.setdefault('USE_MOCK_PACKAGE_REGISTRY', 'false')
    values.pop('GATEWAY_ISSUER_NETWORK', None)
    private_write(env, ''.join(f'{name}={value}\n' for name, value in values.items()))
    print('Configured private RSA key and seven clients; existing credentials preserved.')


if __name__ == '__main__':
    main()
