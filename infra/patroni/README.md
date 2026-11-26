# Patroni image

Run `docker compose build guild-db-1` from the CPR root to build the shared image locally.
The CPR workflow publishes the version in `VERSION` and `latest` for amd64 and arm64.
See the [CPR deployment instructions](../../README.md#storage) for the failover drill.

## A cluster that never bootstraps

On a cold start the PostgreSQL nodes saturate the disk and etcd can answer late. If the reply to a
node's write of the cluster's `initialize` key is lost, Patroni reports `failed to acquire
initialize lock` although the key was written: no node bootstraps, both log `waiting for leader to
bootstrap` and the cluster's healthcheck never passes. Delete the key, and the next loop of either
node bootstraps the cluster:

```bash
docker compose exec etcd-1 etcdctl del /patroni/<scope>/initialize
```

`<scope>` is the cluster's `PATRONI_SCOPE`, for example `battle`. From Git Bash, prefix the command
with `MSYS_NO_PATHCONV=1`, or the path is rewritten into a Windows one. The longer etcd timeouts
(`retry_timeout: 9`) and the etcd heartbeat settings in `compose.yaml` make this rare.
