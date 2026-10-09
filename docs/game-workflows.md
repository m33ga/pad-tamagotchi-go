# Game Workflows

[`collections/game-workflows.postman_collection.json`](../collections/game-workflows.postman_collection.json) plays Tamagotchi Go end to end through the API Gateway. Every request goes to `{{gatewayUrl}}`, and the requests reach all eight services. The per-service collections next to it test one service each. This one tests how the services work together.

## Workflows

| Folder | Story | Services involved | Service-to-service calls through the gateway |
|---|---|---|---|
| 0. Gateway entry and authorization | Probe the gateway: readiness, JWKS, missing, malformed and forged tokens, spoofed identity headers, user and service callers | Gateway, User Management, Tamagotchi, Battle | — |
| 1. Onboarding | Alice, Bob and Carol register; Alice publishes a game package with statistics and battle boosts; everyone joins it, hatches a Tamagotchi and registers a phone | User Management, Package Registry, Tamagotchi, Notification | UMS → Package Registry, Tamagotchi → Package Registry |
| 2. Social life and a PvP battle | Alice and Bob become friends and see each other on the map; stranger Carol appears only within 6 m; Alice challenges Bob and they fight until a knockout; the winner captures the loser's Tamagotchi | User Management, Map, Tamagotchi, Package Registry, Battle, Notification | Map → UMS, Battle → UMS / Tamagotchi / Package Registry |
| 3. Guild life and a Monster Raid | An admin schedules a monster; Alice founds a guild for her package's players, invites Bob, negotiates the guild chat socket; together they defeat the monster and collect rewards | User Management, Package Registry, Guild, Monster Raid, Tamagotchi, Notification | Guild → UMS / Package Registry, Monster Raid → Package Registry / Guild / Tamagotchi / UMS |
| 4. Resilience drills | Service deadline, gateway upstream timeout, unreachable upstream (manual) | Gateway, Tamagotchi | — |

Each run registers new players with a unique suffix, so the collection can be rerun on the same stack without cleanup. A full run takes about 20 seconds on a local stack, most of it the 15 seconds the raid waits for its window to open.

What the collection stands in for:

- **Message queue.** No broker is deployed. Battle, Map, Guild and Monster Raid log or store the events they would publish. The `Deliver … event to Notification` requests send the same envelope to Notification's producer endpoint, using the producing service's own token. Firebase is mocked, so deliveries appear in the Notification logs.
- **Earlier battles.** A battle needs a primary and a secondary Tamagotchi, and players only get secondaries by capturing them. The `Starter gift` requests call the Battle-only ownership transfer with the `battle-service` token. The `Starter purse` requests credit 100 coins so the loser can pay. Battle makes the same calls when it settles a fight.

## Lab 2 coverage

| Grade | Requirement | Where the collection shows it |
|---:|---|---|
| 2 | Run all services with Docker Compose | [Setup](#1-start-the-stack) |
| 5 | Gateway as the entry point, in Compose | Every request goes to `{{gatewayUrl}}`; no service publishes a REST port |
| 6 | All client-to-service and service-to-service REST through the gateway | Folders 1–3. Each request description names the calls it triggers; [trace them](#6-see-what-happened) in the gateway log. For example, `Alice challenges Bob` produces one user call and eleven Battle calls to UMS, Tamagotchi and Package Registry, all under the same correlation ID |
| 7 | WebSocket negotiation through the gateway, direct socket to the service | `3 › Bob negotiates a guild chat connection`, then [Guild chat](#7-guild-chat-over-websocket) |
| 8 | Task timeout and concurrent task limit, with proper errors | Folder 4 and [Resilience drills](#8-resilience-drills) |
| 10 | Authorization at the gateway; `Authorization` not forwarded | Folder 0: missing, malformed, forged and non-Bearer tokens; spoofed `X-User-ID` / `X-Caller-Kind` replaced; junk `Authorization` dropped on public operations; user vs service callers |

Grades 3, 4 and 9 cover the repository, the diagram and CI, not runtime behaviour.

## 1. Start the stack

From the repository root, follow [Run the Services](../README.md#run-the-services):

```bash
test -f .env || cp .env.example .env
```

Replace the `change_me` values in `.env`, then generate the client credentials and start everything:

```bash
python3 scripts/configure_services_auth.py
```

```bash
docker compose pull
```

```bash
docker compose up -d --wait
```

```bash
curl --fail http://localhost:8000/readyz
```

## 2. Import the collection

Use a current Postman desktop app (v11) or Newman 6: the loops rely on `pm.execution.setNextRequest` and `pm.execution.skipRequest`. In Postman, choose **Import** and select `collections/game-workflows.postman_collection.json`. Create an environment, for example `Tamagotchi Go local`, and select it. Keep the secrets below in the environment's **current value** only, so they are never synced or exported.

## 3. Local values

| Variable | Value | Used by |
|---|---|---|
| `gatewayUrl` | `http://localhost:8000` (already the default) | everything |
| `battleClientSecret` | `BATTLE_CLIENT_SECRET` from `.env` | folders 0 and 2 |
| `mapClientSecret` | `MAP_CLIENT_SECRET` from `.env` | folder 2 |
| `guildClientSecret` | `GUILD_CLIENT_SECRET` from `.env` | folder 3 |
| `monsterRaidClientSecret` | `MONSTER_RAID_CLIENT_SECRET` from `.env` | folder 3 |
| `adminEmail`, `adminPassword` | A raid admin account of your choice (see step 4) | folder 3 |

Print the four client secrets with:

```bash
grep -E '^(BATTLE|MAP|GUILD|MONSTER_RAID)_CLIENT_SECRET=' .env
```

A missing value stops the request that needs it with a message naming the variable.

## 4. One-time raid admin

Raid configurations and schedules are admin-only. Package Registry admins are UMS users listed in `PACKAGE_REGISTRY_ADMIN_USER_IDS`. Do this once per deployment:

1. Set `adminEmail` and `adminPassword` to values of your choice.
2. In folder 3, send `Register the raid admin (first run only)` and `Log in the raid admin`. The Postman console prints `PACKAGE_REGISTRY_ADMIN_USER_IDS=<uuid>`.
3. Put that line in `.env` and recreate Package Registry:

   ```bash
   docker compose up -d package-registry-api
   ```

`Find open raid windows` checks the allowlist and tells you exactly this if it is missing.

## 5. Run

**Collection Runner:** run the whole collection, or folders 0–3 in order. The battle turn and raid attack requests repeat themselves until the fight is over. Folder 4 drills report "not armed" unless you arm them (step 8), so they never break a normal run.

**One request at a time:** send the requests top to bottom. For `Take a turn` and `Attack the monster`, keep clicking Send until the battle or raid is no longer `ACTIVE`; the scripts choose the player, Tamagotchi and token. `Bob forfeits` skips itself after a knockout.

**Command line:** export the admin account from step 4 as `RAID_ADMIN_EMAIL` and `RAID_ADMIN_PASSWORD` in your shell, then load `.env` and run Newman:

```bash
set -a; . ./.env; set +a
```

```bash
npx newman@6 run collections/game-workflows.postman_collection.json --env-var "battleClientSecret=$BATTLE_CLIENT_SECRET" --env-var "mapClientSecret=$MAP_CLIENT_SECRET" --env-var "guildClientSecret=$GUILD_CLIENT_SECRET" --env-var "monsterRaidClientSecret=$MONSTER_RAID_CLIENT_SECRET" --env-var "adminEmail=$RAID_ADMIN_EMAIL" --env-var "adminPassword=$RAID_ADMIN_PASSWORD"
```

Add `--folder "<folder name>"` once per folder to run only some of them.

User tokens last 15 minutes and service tokens 5 minutes. After a long pause, resend the `Log in …` and `Get … token` requests of the folder you are in.

## 6. See what happened

Every request logs its `X-Correlation-ID` to the Postman console. The gateway writes one log line per request with that ID, the service and the caller kind. Grepping for the ID of a user request also shows the service-to-service calls it caused (`caller_kind: service`). Try it on `Alice challenges Bob` or `Alice starts the guild raid`:

```bash
docker compose logs api-gateway | grep <correlation-id>
```

Other evidence:

| What | Command |
|---|---|
| Push notifications produced from the delivered events | `docker compose logs notification-api \| grep Push` |
| Proximity event Map would publish when Carol came within 6 m | `docker compose logs map-api \| grep -i proximity` |
| Raid lifecycle events Monster Raid would publish | `docker compose logs monster-raid-api \| grep raid\.` |
| Battle turns and raid hits | Postman console |

## 7. Guild chat over WebSocket

`Bob negotiates a guild chat connection` is the only part the gateway handles. It returns Guild's public socket URL (`ws://localhost:8081/...`, not the gateway) and a single-use ticket valid for 60 seconds. The console prints the full `…?ticket=…` URL. Within 60 seconds, open a Postman **WebSocket** request to that URL, or use `wscat`:

```bash
wscat -c '<url printed in the console>'
```

Send:

```json
{"type": "guild.chat.message.send.v1", "clientMessageId": "a30b3bd2-3c74-4fe1-9f53-c67ea72171db", "content": "Ready for the raid?"}
```

Guild stores the message and broadcasts `guild.chat.message.created.v1` to every connected member. `Guild chat history` then returns it over REST. Connecting a second time with the same ticket is refused with `401`. Send the negotiation request again for a fresh ticket, for example with Alice's token for a second participant.

## 8. Resilience drills

Run the Docker commands from the repository root. Each Postman drill passes when its error appears, and only reports "not armed" otherwise.

| Drill | Arm | Expected | Undo |
|---|---|---|---|
| Service deadline | `docker compose pause tamagotchi-db` | `504 REQUEST_TIMEOUT` from Tamagotchi after its 4 s deadline, before the gateway's 5 s | `docker compose unpause tamagotchi-db` |
| Gateway upstream timeout | `docker compose pause tamagotchi-api` | `504 UPSTREAM_TIMEOUT` from the gateway after 5 s | `docker compose unpause tamagotchi-api` |
| Upstream down | `docker compose stop tamagotchi-api` | `502 UPSTREAM_UNAVAILABLE` | `docker compose start tamagotchi-api` |

Concurrency limits need parallel requests, so use the shell. Log in first, for example as the raid admin:

```bash
TOKEN=$(curl -s http://localhost:8000/user-management/api/v1/auth/sessions -H 'Content-Type: application/json' -d "{\"email\":\"$RAID_ADMIN_EMAIL\",\"password\":\"$RAID_ADMIN_PASSWORD\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
```

**Gateway per-service limit (64).** With `tamagotchi-api` paused, each request holds a gateway slot for 5 seconds. Of 100 parallel requests, 64 time out with `504` and the rest are refused immediately with `503 CONCURRENCY_LIMIT_REACHED` and `Retry-After: 1`:

```bash
docker compose pause tamagotchi-api
```

```bash
seq 100 | xargs -P 100 -I{} curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" http://localhost:8000/tamagotchi/api/v1/tamagotchi-combat-types | sort | uniq -c
```

```bash
docker compose unpause tamagotchi-api
```

The gateway logs one `limit_reached` line per refused request: `docker compose logs api-gateway | grep limit_reached`.

**Service's own limit.** Set `MAX_CONCURRENCY=8` in `.env`, then run `docker compose up -d tamagotchi-api` and `docker compose pause tamagotchi-db`. Twenty parallel requests that need the database now give 8 × `504 REQUEST_TIMEOUT` and 12 × `503 CONCURRENCY_LIMIT_REACHED`, both answered by Tamagotchi itself:

```bash
seq 20 | xargs -P 20 -I{} curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" http://localhost:8000/tamagotchi/api/v1/tamagotchis/00000000-0000-0000-0000-000000000000 | sort | uniq -c
```

Afterwards run `docker compose unpause tamagotchi-db` and restore `MAX_CONCURRENCY=64`. Wait until `docker compose ps tamagotchi-db` shows `healthy` again, then run `docker compose up -d --wait tamagotchi-api`. If you recreate the API right after the unpause, Compose may still see the database as unhealthy and leave `tamagotchi-api` only created, not started.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Set … to … from the deployment .env` | Fill in the named variable (step 3) |
| `Find open raid windows` fails with 403 | The admin is not allow-listed (step 4) |
| `Admin schedules the raid window` returns `409 SCHEDULE_CONFLICT` | Another raid window overlaps. Resend `Find open raid windows`; the next request closes every open one |
| `503 PACKAGE_REGISTRY_UNAVAILABLE` or `503 USER_SERVICE_UNAVAILABLE` | A collaborator is down; check `docker compose ps` |
| `401 INVALID_TOKEN` in the middle of a manual run | The token expired; resend the folder's login or token requests |
| The battle ends with `Bob forfeits` instead of a knockout | The turn loop stopped after repeated rejections or 150 actions; the console shows why. Settlement is still checked |
