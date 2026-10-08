# User Management Lab 2 integration (#45)

UMS signs RS256 user and service tokens. The gateway verifies them against
`http://user-management-api:8080/.well-known/jwks.json`, strips bearer and caller
identity headers and sends verified identity headers to UMS. Its public operations
are key discovery, registration, login, refresh and client credentials; they are
listed explicitly in `config/gateway.yaml`. The complete wire contract, clients,
scopes and failure shapes are in the README's User Management section and
`docs/schemas/user-management-service.json`.

## Private configuration

1. Copy `.env.example` to `.env` only when `.env` does not already exist. Fill the
   database credentials. Keep existing database passwords for existing volumes.
2. Run `python3 scripts/configure-user-management-oauth.py`. It creates or reuses
   an RSA private key and seven independent client secrets without printing them.
   Only SHA-256 hashes are inserted into `.env`; existing secrets are reused.
3. Back up `.env` and `secrets/` using an encrypted backup or a password manager.
   They are excluded from Git. The private directory is mode 700; credential files
   are mode 600. The individual key file is readable by the non-root container;
   its parent host directory remains private.
4. Each `secrets/<client-id>.env` belongs only in the corresponding service's
   private configuration. Adapt the variable names to that client's implementation.
   Do not load all plaintext client secrets into a shared environment or into UMS.
   Clients cache the token and refresh it when fewer than 30 seconds remain.
5. Set `GATEWAY_IMAGE` in `.env` to the complete gateway image supplied by its owner.
   The gateway repository currently builds images in CI without publishing them.
   For local testing, build its Dockerfile as `grdz/gateway:dev` and use that tag.

The UMS private key must never be mounted into the gateway or other services.
`config/service-clients.yaml` contains only environment references to hashes.
Changing a hash or enabled flag requires restarting UMS, which upserts the registry.
For secret rotation, temporarily include both hashes, restart, roll the client and
then remove the old hash. For signing-key rotation, retain the old public JWKS in a
separate read-only mount and set `JWT_PREVIOUS_PUBLIC_KEYS_PATH` until old tokens
have expired. Never distribute the previous private key.

## Deployment

The UMS service PR must first pass CI and be approved and merged: its workflow
publishes `sanda2004/user-management-service:2.0.0` and `latest`. Repository secrets
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are required for publishing.

```sh
docker compose -f compose.yaml -f compose.gateway.yaml up -d --wait
curl --fail http://localhost:8000/readyz
curl --fail http://localhost:8000/user-management/.well-known/jwks.json
```

For local images that have already been built, add `--pull never`. UMS and its
database publish no host port and share the internal `issuer` network. The gateway
joins that network and the deployment's service network. Keep other services'
Lab 1 ports until their respective Lab 2 migrations; #45 only changes UMS.
Package Registry must also complete its header-identity migration before the full
live deployment can accept UMS registration calls. UMS sends a locally signed
`user-management-service` token through the gateway on those calls.

The token endpoint is `POST /user-management/api/v1/oauth2/token` and accepts
URL-encoded `grant_type=client_credentials`, `client_id`, `client_secret`, and an
optional configured `scope`. No external OAuth portal or redirect URI is needed.
Public operations ignore bearer tokens; protected calls require one. Clients must
never send identity headers as a substitute for a bearer token.

The OpenAPI file describes gateway-facing calls. The service rejects direct calls
without `X-Caller-Kind`; its internal health and JWKS endpoints are exceptions.

## Verification

Pull the published UMS image and build the verified gateway for local checks:

```sh
docker pull sanda2004/user-management-service:2.0.0
docker build -t grdz/gateway:dev ../gateway
python3 tests/user_management_gateway_smoke.py
```

The UMS submodule is pinned to the merged service implementation. For development
before publication, build its Dockerfile locally instead of pulling the release.

The smoke test creates temporary keys, secrets, a separate Compose project and a
fresh PostgreSQL volume. It runs the actual gateway and UMS images. An HTTP fixture
stands in for Package Registry and checks verified service identity and correlation
on both outbound operations. Tests cover seven clients, OAuth failure shapes, key
discovery, login, owner checks, forged identity headers, refresh revocation after
logout, balance permissions and absence of a UMS host port. It checks that client
secrets do not occur in logs, then removes its containers, networks and volume.
It does not consume the real `.env`, database or client credentials.

UMS's own tests cover key and secret rotation, per-client rate limits, fail-fast
concurrency, deadlines including a locked database, and recovery afterwards.
Live checks against the other seven services belong to their integration work.
If Docker on macOS cannot read a cloud-offloaded signing key, rerun the setup
script to materialize the same key locally, then recreate the UMS container.

## Pull requests

The service PR references `m33ga/pad-tamagotchi-go#45`; the CPR PR closes #45 only
once the required image and dependencies are available and integration checks pass.
PRs are created manually, require approval and green CI, and use squash merge.

PR CI validates the OpenAPI and Compose isolation rules. After the UMS image is
published, run the **User Management Lab 2** workflow manually to repeat the real
gateway integration on GitHub Actions. It pins the gateway source to the tested
`fb646400a86b8b987c89eb2cfa9ff922bad63641` commit; update the pin when adopting a
new gateway version.
