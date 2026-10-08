# Guild and Package Registry: Lab 2 verification

Checked locally on 2026-10-08 against issues
[#49](https://github.com/m33ga/pad-tamagotchi-go/issues/49) and
[#50](https://github.com/m33ga/pad-tamagotchi-go/issues/50).
This is a progress report, not confirmation that either issue is complete.

## Implemented and exercised locally

- Registry: gateway identity is required; UUID bearer tokens and caller-supplied
  role headers do not grant access. Registration writes and per-user registration
  listing allow User Management only. Raid schedule listing allows Monster Raid
  or configured administrators. Developer/moderator permissions come from the
  database; registration replay and mismatched-key conflicts were tested.
- Guild: member-only chat negotiation, 32-byte base64url tickets with a 60-second
  lifetime, expired/missing/reused/wrong-guild ticket rejection. Twelve parallel
  handshakes using one ticket produced exactly one successful connection.
  Socket identity ignores caller-provided identity headers and comes from the
  ticket. Broadcast, message deduplication and message persistence were tested.
- Guild: Monster Raid can read membership/roster; another service cannot.
  A path user ID does not impersonate the authenticated caller.
- Both services: 4-second default REST deadlines, below the gateway's default
  5-second upstream timeout; immediate concurrency rejection with Retry-After.
  Timed-out work retains its slot while it finishes. Correlation IDs are
  preserved rather than replaced merely because they are not UUIDs.
- Guild: migration from UUID to text outbox correlation IDs preserves existing
  events and can be run repeatedly. Missing guild negotiation uses
  GUILD_NOT_FOUND as specified.
- Unit-only statement coverage is now **87.0% for Guild** and **87.5% for
  Package Registry**, measured across each entire Go module with the race
  detector (`-count=3`), without TEST_DATABASE_URL or TEST_GATEWAY_URL. CI enforces 80%.
  Strict PostgreSQL mocks exercise real handlers/stores with failure injection
  at each database step, transaction rollback, permissions, pagination,
  validation, idempotent registration and message replay. WebSocket unit tests
  cover invalid tickets, errors, broadcast, revoked membership and disconnects.
  A subsequent PostgreSQL-backed race-test regression also passed in both
  repositories, using unique schemas on a separate disposable database.
- OAuth verifier unit tests cover form credentials, caching, early refresh,
  one retry after 401, correlation forwarding and remaining-deadline propagation.
  These unit tests use a controlled token/dependency transport.
- A separate disposable Docker run passed against the **actual gateway** and
  published **sanda2004/user-management-service:2.0.0** issuer with all external
  mocks disabled. Verified: real user registration/login, 300-second service
  tokens for Guild/Registry/Monster Raid, package creation and permissions,
  moderator revocation, rejected forged identity headers, real Guild dependency
  checks, invitations/acceptance, Monster Raid roster access, negotiated direct
  WebSocket URLs, ticket reuse rejection, broadcast/deduplication/persistence,
  ownership transfer and deleted-guild socket shutdown. The issuer image digest
  was sha256:18e357c00973b6a6ea68b5cc7f8e940d0654e462afdd346f947d1be4f4ce857d.
  Gateway and owned-service images were built locally, not downloaded releases.
- After reconciling with the shared deployment on main, the same disposable
  end-to-end scenario passed again with published `grdz/gateway:2.0.1`
  (digest `sha256:bc60b8e85d4c9b3e8b135b8403d73be0774db7691cbdfff76bf08bcb7db4ac3b`).
  Owned services were still local audit builds, not published release evidence.
- GitHub Actions on both private-service PRs passed unit/race tests, the 80%
  coverage gate, PostgreSQL integration tests, vet, executable and Docker builds.
- Configuration accepts the shared setup script's OAUTH_CLIENT_ID and
  OAUTH_CLIENT_SECRET. Compose loads each service's own private credential file.
  Neither REST listener nor either database publishes a host port; only the
  separate Guild WebSocket listener does. Gateway and services share a network.
- Go race tests and vet pass. Both services compile for Linux AMD64 and ARM64.
  Local Docker images build and pass health/identity/listener smoke checks.
  These checks do not verify the published multi-platform manifests.

## Reproducible checks

In either private service repository:

1. Run `env -u TEST_DATABASE_URL -u TEST_GATEWAY_URL go test -race -coverpkg=./... -coverprofile=unit.cover ./...`,
   then `go tool cover -func=unit.cover`.
2. Set TEST_DATABASE_URL to a disposable PostgreSQL database; the test account
   must be able to create schemas. Run
   `go test -race -coverpkg=./... -coverprofile=integration.cover ./...`.
3. Run `go vet ./...` and `go tool cover -func=integration.cover`.

Database tests use isolated schemas and remove only those schemas. Without
TEST_DATABASE_URL they explicitly skip, so a unit-only green run is not evidence
that the PostgreSQL or WebSocket integration tests ran. The CI configuration now
provides PostgreSQL, runs both suites and uploads the separate coverage reports.

For the real gateway/issuer check, build the current gateway and owned services
into local image tags, then run from the CPR:

```sh
python3 scripts/verify_owned_services_e2e.py \
  --gateway-image YOUR_LOCAL_GATEWAY_IMAGE \
  --guild-image YOUR_LOCAL_GUILD_IMAGE \
  --registry-image YOUR_LOCAL_REGISTRY_IMAGE
```

This requires Docker Compose, Go, openssl, and the initialized Guild submodule.
The script creates a uniquely named Compose project with tmpfs databases,
generated fixture credentials/key, and loopback-only gateway/WebSocket ports.
It does not read the project's `.env` or `secrets/`. A bootstrap package is seeded
only into its disposable Registry database; users and subsequent resources are
created through the gateway. The script runs Guild's opt-in
`TestLiveGatewayIssuer`, then removes its containers/network and fixture files.
This checks deployment behavior separately from unit coverage.

In the CPR, run `python3 scripts/test_owned_gateway_deployment.py`.
This validates the Compose model using placeholder values without loading private
credential files or starting the deployment.

Run `node --test scripts/test_owned_collections.cjs` for the collection
regressions. These validate operation-specific token selection, gateway URLs,
unpopulated credential variables, and script/ID capture across two iterations in
a shared JavaScript context using synthetic responses. They do not send HTTP
requests or replace a full Postman run.

## Remaining before claiming completion

- Run the Postman collections against the final merged/published deployment.
  The automated real-stack test exercises the trust boundary and principal
  business flows, but is not a claim that every imported Postman request was run.
- Review and merge private-service PRs only after approval and successful CI.
  Confirm Docker Hub Actions secrets, successful automatic publication after
  merge, and that the lab-version/latest tags identify the intended release on
  both AMD64 and ARM64.
- Update the CPR submodule pointers to reviewed service commits and merge the
  CPR deployment/docs PR after approval. Do not push directly to main.
- Verify the final published images from a fresh pull and another teammate's
  environment before checking off the issues.

The test runs do not change existing application databases. Existing Lab 1
containers are not evidence that the new Lab 2 deployment is running.
