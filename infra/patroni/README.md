# PostgreSQL high availability

Eight independent primary/replica pairs share a three-member etcd quorum. HAProxy preserves each
existing database host name, routes 5432 to `/primary`, and prefers `/replica` on 5433 with a primary
fallback. Application credentials and connection strings stay the same. Bootstrap adds the
restricted `analytics_reader` and `monitoring` roles; service migrations grant the analytics views.

The source is PostgreSQL 17.12 (pinned multi-platform image digest), Patroni 4.1.5, HAProxy 3.2.27
and etcd 3.6.17. The SQL exporter is 0.21.1; its pinned custom-query support supplies prepared
transaction count/age and replay lag not supplied by Patroni. It is deprecated upstream, so check
this query interface before upgrading the exporter. No new listener is published on the host.

## Configuration and limits

`patroni.yml` is rendered by `configure.py`, after dropping root, into a 0600 runtime file.
PostgreSQL owns its data directory; passwords are passed through environment variables, never
interpolated into a shell command or committed. Bootstrap SQL quotes role and database identifiers
and uses bound password values. `postgres` is reserved for Patroni; the application owner is not a
superuser. Use distinct private values for the five infrastructure passwords in `.env.example`.

`ttl=20`, `loop_wait=2`, `retry_timeout=5` satisfy Patroni's enforced minimum and timeout inequality.
The originally requested ttl of 10 is clamped to 20 by Patroni. A crash can therefore interrupt
connections for approximately 20 seconds plus health checks, rather than a guaranteed 10 seconds.
The tests report actual recovery time. No privileged watchdog is required on the Docker host;
this implementation does not claim fencing against every frozen-agent or paused-host failure.
`bootstrap.dcs` initializes a new scope only; changing its template does not replace the dynamic
configuration of an existing cluster. Use `patronictl edit-config` for an intentional runtime change.

Replication is asynchronous. Surviving a failover with the data checked in these tests does not
prove zero data loss: the tests explicitly wait for their WAL to be replayed before crashing the
leader. Only User Management and Package Registry enable 64 prepared transactions. Distributed
transaction participants must still consult their coordinator to resolve in-doubt transactions.

Data checksums and WAL hints support `pg_rewind`. A divergent former leader is rewound, or recloned
if necessary, when started again. Independent volumes are used for both nodes. Legacy standalone
volumes are retained, not automatically imported or deleted. Follow the root README's backup and
restore procedure **before** replacing a populated deployment.

## Test and demonstrate

Use a separate checkout with its own private `.env`, generated service credentials and RSA key.
The root Compose model requires those files even when only database services are selected. Do not
reuse a populated deployment or its project name. The integration test permits only an explicitly
named `pad-patroni-test-*` or `pad-lab5-ha*` project, writes only probe tables/views, kills its primary,
and restarts that node in a `finally` block. It never deletes volumes or touches another project.

```sh
docker compose config --quiet
docker compose build guild-db-1
docker run --rm --entrypoint python -v "$PWD/infra/patroni:/contract:ro" \
  grdz/patroni:5.0.0 -m unittest discover -s /contract/tests -v
# First prove the Guild pilot.
docker compose -p pad-patroni-test-local up -d --wait --wait-timeout 240 guild-db-exporter
python3 infra/patroni/tests/integration.py --project pad-patroni-test-local --cluster guild
# Then bring up all eight and test the same behavior on each.
docker compose -p pad-patroni-test-local up -d --wait --wait-timeout 240 \
  broker-db-exporter user-management-db-exporter battle-db-exporter monster-raid-db-exporter \
  guild-db-exporter package-registry-db-exporter tamagotchi-db-exporter notification-db-exporter
python3 infra/patroni/tests/integration.py --project pad-patroni-test-local
# Exercise application connection pools through the gateway too.
docker compose -p pad-patroni-test-local up -d --wait --wait-timeout 240 \
  api-gateway user-management-api package-registry-api guild-api-1 guild-api-2
python3 infra/patroni/tests/gateway.py --project pad-patroni-test-local --gateway-url http://127.0.0.1:8000
docker compose -p pad-patroni-test-local stop
```

The tests assert one leader and one streaming replica, primary/read routing, read-only analytics
access, replayed data survival, promotion through the unchanged proxy, read fallback, automatic
rejoin on the new timeline and continued writes. Participant clusters additionally test prepared
state surviving promotion, `COMMIT PREPARED` and `ROLLBACK PREPARED`. The eight SQL exporters and
16 Patroni metrics targets feed Grafana's Databases dashboard through the collector.

The gateway test creates a unique account and Guild/Package resources, kills each database
primary, and proves reads and new writes recover through the public API without restarting
the application containers. Test account credentials remain in memory. It waits for the broker
to list the instances, because a liveness response alone does not prove registration completed.
It logs in again after each promotion so a paused demonstration and an expired user token do
not obscure the database recovery check; normal authentication remains enabled.

For a manual failover use `patronictl list` from either node to find the current leader, then kill
that service with Compose and start it again. A normal test leaves the other node as primary;
do not assume node 1 is always primary. An application may see failed requests already in flight;
its pool must reconnect without exiting. Run an actual gateway business request before and after
the database failure when validating the full application stack.

## Image publication

The CPR Patroni workflow builds and tests pull requests. On a main merge affecting this image,
after the tests pass, it publishes `grdz/patroni:<VERSION>` and `latest` for amd64 and arm64, then
creates a `patroni-v<VERSION>` release pointing at the exact CPR commit. Repository secrets
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` must have write permission to `grdz/patroni`; a personal
account without that namespace permission cannot publish it. Version tags are immutable: bump
`VERSION` and the Compose image pin together for each subsequent change. No image has been
published merely because a local build succeeded.
