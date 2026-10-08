# Configuration

The deployment uses `compose.yaml` for the gateway and all services. Containers
communicate by service name on the default Compose network. The gateway's host
port and image are selected with `GATEWAY_PORT` and `GATEWAY_IMAGE`. Route URLs and
public operations are configured in `config/gateway.yaml`.

## Environment

Copy `.env.example` to `.env` only if `.env` does not already exist. Replace the
placeholder database and cache credentials, and select the gateway image supplied
by its owner. A prebuilt local image tag can also be used; start with `--pull never`
when testing local images. Keep existing database passwords when reusing volumes.

The template groups settings by service and shared purpose. Service settings are
loaded from `.env`; Compose `environment` entries adapt values where an image uses
different names or a container-specific address. The User Management API and
database publish no host ports. Other published development ports are listed in
the README.

`REQUEST_TIMEOUT_SECONDS` and `MAX_CONCURRENCY` configure the issuer's request
deadline and admission budget, defaulting to 10 seconds and 64 requests. Other
services may expose their own settings for the same request handling contract.
`JWT_SIGNING_KEY` is retained for the current Battle image and its direct-call
collection. It is not used to issue system tokens; those use asymmetric signing.

## Service Authentication

Run from the repository root:

```sh
python3 scripts/configure_services_auth.py
```

Python 3.9 or newer, OpenSSL and Git are required. The script creates or reuses an
RSA signing key and seven independent client secrets without printing them. It
preserves existing credentials and writes the SHA-256 hashes to `.env` for the
mounted client registry in `config/service-clients.yaml`.

The signing key lives at `secrets/jwt-private.pem` and is mounted only into the
token issuer. `JWT_PRIVATE_KEY_PATH` is its path inside the container; `JWT_KEY_ID`
identifies its public key. The gateway receives public keys through JWKS and must
never receive the private key.

Each `secrets/<client-id>.env` belongs in the corresponding service's private
configuration. It contains `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET` and
`OAUTH_TOKEN_URL`; adapt these names to that service's configuration interface.
Do not load every client's plaintext secret into a shared environment. Clients
request a token through the gateway, cache it and refresh it when fewer than
30 seconds remain. Claims, scopes and identity headers are defined in the
README's authentication contract.

## Secret Storage and Rotation

Keep `.env` and `secrets/` out of Git. Back them up in encrypted storage or a
password manager. Share each client credential only with its service owner; keep
the issuer's private key with the deployment operator. The private directory is
mode 700 and credential files are mode 600. The key file is readable by the
non-root container inside that private host directory.

For client secret rotation, temporarily configure both hashes, restart the issuer,
switch the client to the new secret, then remove the old hash. For signing-key
rotation, publish both old and current public keys until existing tokens expire.
Never distribute an old private key as part of public key rotation.

If Docker on macOS cannot read a cloud-offloaded signing key, rerun the setup
script. It materializes the existing key without generating a replacement.
