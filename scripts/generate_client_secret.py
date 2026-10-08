#!/usr/bin/env python3
"""Print a random OAuth client secret and the SHA-256 hash used by the issuer."""
import argparse
import hashlib
import secrets

CLIENTS = (
    'battle-service', 'monster-raid-service', 'map-service', 'guild-service',
    'tamagotchi-service', 'package-registry-service', 'notification-service',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client_id', choices=CLIENTS)
    args = parser.parse_args()
    prefix = args.client_id.removesuffix('-service').replace('-', '_').upper()
    secret = secrets.token_urlsafe(32)
    print(f'# {args.client_id}: client configuration in local .env')
    print(f'{prefix}_CLIENT_SECRET={secret}')
    print('# User Management: issuer configuration in local .env')
    print(f'{prefix}_CLIENT_SECRET_HASH={hashlib.sha256(secret.encode()).hexdigest()}')
    print('# UMS authenticates this client using the hash; the client uses the plaintext.')


if __name__ == '__main__':
    main()
