# User Management and Battle release verification

Verified against the combined Compose stack with Broker 4.5.1, Gateway 4.3.1,
User Management 4.1.0, Guild/Package Registry 4.0.0, Map 4.3.0,
Monster Raid 4.4.1 and Tamagotchi/Notification v4.2.0.
Battle 4.0.2 fixes the event payload casing found during these checks.

## Business checks

- User Management client collection: 20 requests, 22 assertions passed.
- Registration with `initialPackageId` and later package membership both reached
  the real Package Registry through gRPC over `Broker.Send`.
- Battle client collection: 10 requests and 10 assertions passed, including
  challenge, acceptance, attack and forfeit settlement.
- A separate combat scenario reached `COMPLETED` by attacking through the client
  API. Currency, each participant's XP and captured ownership matched the result.
- With Tamagotchi paused before settlement, Battle remained `SETTLING`. After
  unpausing it, the worker completed settlement. Wallets, all four XP awards and
  ownership were checked against their pre-battle values; no reward was repeated.
- Real `raid.completed.v1` delivery credited each wallet once. A second event ID
  with the same raid reference did not credit it again. Publishing with a Battle
  token while spoofing `monster-raid` was rejected by the consumers.
- Notification persisted friend-request, battle-request and battle-completion
  notifications. Firebase delivery remains the service's mock.
- Tempo contained a shared trace across Gateway, Broker, Battle, User Management,
  Tamagotchi and Notification.

## Release correction

Battle 4.0.1 serialized outbox payloads using PascalCase. Notification correctly
rejected these as malformed. Battle 4.0.2 writes camelCase and rehydrates typed
payloads before publishing, including pending rows from the older image. The
regression suite covers both event types and both persisted casings: 48 unit tests
pass, alongside the service CI integration and image-build checks.

## Local environment

The isolated Docker Desktop review stack uses private generated credentials and
its own volumes. User Management and Battle ran with two replicas. To fit the
local 4 GB Docker VM, Tamagotchi and Notification ran with one replica each;
tracked Compose retains the configured replicas. Those two peer images require
amd64 emulation on this Apple Silicon machine. Cold first-use requests exceeded
budgets during warm-up; the completed client collections use the unchanged
production request deadlines.

No credentials or populated Postman environment are committed.
