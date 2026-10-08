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
- OAuth verifier unit tests cover form credentials, caching, early refresh,
  one retry after 401, correlation forwarding and remaining-deadline propagation.
  These tests use a controlled token/dependency transport, not the team's issuer.
- Configuration accepts the shared setup script's OAUTH_CLIENT_ID and
  OAUTH_CLIENT_SECRET. Compose loads each service's own private credential file.
  Neither REST listener nor either database publishes a host port; only the
  separate Guild WebSocket listener does. Gateway and services share a network.
- Go race tests and vet pass. Both services compile for Linux AMD64 and ARM64.
  Local Docker images build and pass health/identity/listener smoke checks.
  These checks do not verify the published multi-platform manifests.

## Reproducible checks

In either private service repository:

1. Run `go test -race -coverprofile=unit.cover ./...`.
2. Set TEST_DATABASE_URL to a disposable PostgreSQL database; the test account
   must be able to create schemas. Run
   `go test -race -coverpkg=./... -coverprofile=integration.cover ./...`.
3. Run `go vet ./...` and `go tool cover -func=integration.cover`.

Database tests use isolated schemas and remove only those schemas. Without
TEST_DATABASE_URL they explicitly skip, so a unit-only green run is not evidence
that the PostgreSQL or WebSocket integration tests ran. The CI configuration now
provides PostgreSQL, runs both suites and uploads the separate coverage reports.

In the CPR, run `python3 scripts/test_owned_gateway_deployment.py`.
This validates the Compose model using placeholder values without loading private
credential files or starting the deployment.

## Remaining before claiming completion

- Unit-only statement coverage: Guild **16.8%**, Registry **14.0%**.
  Combined unit/integration statement coverage: Guild **48.3%**, Registry
  **46.7%**. Neither result establishes the 80% unit-test coverage requirement.
  Extend meaningful unit tests across business rules, handlers and storage
  behavior; do not substitute gateway coverage or integration coverage.
- Run the integrated stack with the actual gateway and User Management issuer,
  real registered client credentials, and mocks disabled. Exercise both Postman
  collections, including cross-service calls and the negotiated WebSocket URL.
  Current service integration tests provide gateway-style trusted headers
  directly; they do not prove the deployed token trust boundary.
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
