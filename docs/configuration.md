# Configuration

The deployment uses one `compose.yaml`. The gateway joins `edge` and `internal`;
all other services join only `internal`, which is marked `internal: true`.
Only `GATEWAY_PORT` and the separate `GUILD_CHAT_PORT` are published to the host.
Guild's REST listener stays on port 8081 inside its container; its socket listener
uses port 8082. The `guild-chat` Nginx relay joins both networks and publishes only
the socket path; other paths return 404. This is necessary because Docker does not
publish ports for containers connected only to an internal network. Guild itself
never joins `edge`. `GUILD_PUBLIC_WS_URL` is the public socket address clients receive.

## Environment

Copy `.env.example` to `.env` if it does not exist, then replace the database and
cache placeholders. Preserve passwords belonging to existing volumes.
`GATEWAY_IMAGE` defaults to the published `grdz/gateway:2.0.0` image.
The currently published Tamagotchi and Notification images target `linux/amd64`;
Compose selects that platform explicitly so Docker Desktop can emulate them on
Apple Silicon. The other images use their native platform.

`GATEWAY_URL=http://api-gateway:8080` is the address for service-to-service calls;
client requests use the gateway's published address and the service prefix.

Compose passes each API only its own database/cache settings and client credential.
The issuer receives the seven secret hashes and its private key. The gateway
receives neither client secrets nor the private signing key; it retrieves public
keys from User Management through JWKS. Do not add a shared `.env` as `env_file`
to API containers, because that would disclose other clients' secrets to them.

`REQUEST_TIMEOUT_SECONDS` and `MAX_CONCURRENCY` configure service admission and
deadlines. Gateway budgets and upstream timeouts are configured separately in
`config/gateway.yaml`, along with route URLs and the public-operation allowlist.

## Generate Client Credentials

Generate a 32-byte random base64url secret and its SHA-256 hash in one command:

```sh
just gen-client-secret battle-service
# Without just: python3 scripts/generate_client_secret.py battle-service
```

The output labels both destinations:

```text
BATTLE_CLIENT_SECRET=<plaintext>       # local .env; passed only to Battle
BATTLE_CLIENT_SECRET_HASH=<sha256-hex> # local .env; passed only to UMS
```

Use the corresponding client ID for each of the seven services. Client IDs and
allowed scopes are recorded in `config/service-clients.yaml`. The generator does
not write either value to Git. Keep its output private.

Alternatively, prepare all credentials and the signing key together:

```sh
python3 scripts/configure_services_auth.py
```

The setup script preserves existing credentials, generates missing ones, and
writes both plaintexts and hashes to the ignored local `.env` without printing
them. It also maintains private `secrets/<client-id>.env` files for compatibility
with independent service runs. Compose maps each matching plaintext to
`CLIENT_SECRET` and `OAUTH_CLIENT_SECRET`; it never loads another client's file.

## Signing Key

The setup script generates or reuses an RSA private key at
`JWT_PRIVATE_KEY_FILE` (default `./secrets/jwt-private.pem`). Only User Management
mounts it at `JWT_PRIVATE_KEY_PATH=/run/secrets/jwt-private.pem`. `JWT_KEY_ID`
identifies its public key. The committed template contains a file path, never PEM
key material. A PEM file can also be generated manually with:

```sh
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/jwt-private.pem
```

The issuer loads client hashes from the mounted `config/service-clients.yaml`.
Services request their tokens at
`GATEWAY_URL/user-management/api/v1/oauth2/token` using form-body client credentials.
They cache tokens and refresh them before expiry; callers never sign tokens locally.

## Storage and Rotation

Keep `.env` and `secrets/` outside Git. Back them up in encrypted storage or a
password manager. Share each client credential only with its service owner; keep
the issuer's private key with the deployment operator. The private directory uses
mode 700 and credential files mode 600. The key file is readable by the non-root
container inside that private host directory.

For secret rotation, add the new hash alongside the old one in the issuer's
registry, restart the issuer, update the corresponding client secret, recreate
that service, and remove the old hash. Update the matching `.env` plaintext before running the setup script;
it synchronizes the client's private file and issuer hash. During signing-key rotation, publish both public keys until old tokens
expire. Never distribute private keys as public rotation material.

If Docker on macOS cannot read a cloud-offloaded key, rerun the setup script.
It materializes the existing key without generating a replacement.
