# Tamagotchi Go

Virtual pets and beating up your friends. A distributed system.

Players raise Tamagotchis in apps of their own creation, all connected to a common backend where these worlds meet: encounter nearby players, battle their creatures, join guilds and take down raid monsters together, while keeping your own pet from starving to death.

Developed for the PAD (Distributed Applications Programming) course at FAF, Technical University of Moldova.

## Service Boundaries

### User Management Service

Microservice responsible for the global identity of every user and their account data (username, password, email, and the package(s) they are registered with). Handles authentication and security, and maintains each user's social graph of friends and enemies.

Each user holds two currencies: a **local currency**, whose value and means of acquisition are determined by the individual package the user belongs to, and a **global currency**, shared across the entire ecosystem and primarily earned through battles and other global activities.

This service is the authority for questions such as *"Who is this user?"*, *"Are these two users friends?"*, and *"Does this user have enough global currency?"*. Other services consult it to authenticate players and to resolve relationships and balances before performing currency-affecting operations.

### Tamagotchi Service

Maintains the globally relevant state of all Tamagotchis. A user has a **primary Tamagotchi**, initially provided by the package they downloaded, and may acquire **secondary Tamagotchis** originating from other users or packages. Crucially, secondary Tamagotchis are not new entries but **references to existing ones**.

For each Tamagotchi it stores identity, owner, combat type, level, sprite references, and package-local health statistics (e.g. hunger, tiredness, happiness). These statistics are deliberately **not normalized**, as their management is package-specific.

The service defines six predefined combat types with a cyclic type-advantage system:

```
Flame → Nature → Earth → Electric → Water → Shadow → Flame
```

It provides combat type, level, and health information to the **Battle Service** and **Monster Raid Service** when computing damage, and owner/reference resolution to the **User Management Service**.

### Battle Service

Executes the actual turn-based PvP combat after a match has been created. Each player selects one **primary** and one **secondary** Tamagotchi and may equip available battle boosts.

Combat calculates:

- starting health based on Tamagotchi levels,
- damage based on primary/secondary level, type advantage/disadvantage, equipped boosts, and current Tamagotchi health stats,
- the current battle state and turn.

At the end of the battle, the **winner** receives global currency, XP, and the loser's primary Tamagotchi. The **loser** loses some global currency and receives a smaller amount of XP. XP is distributed between the primary and secondary Tamagotchis following a defined rule (e.g. 60/40).

This service consults the **Tamagotchi Service** for combat stats, XP grants, and ownership transfer; the **User Management Service** for global-currency credit and debit operations; and the **Package Registry Service** for package-specific combat bonuses.

### Map Service

Receives continuous geolocation updates from the user's application. It stores the user's latest known coordinates and timestamp, discarding or ignoring stale locations.

It provides a map of nearby users: friends and enemies are always visible, while unknown users become relevant only when they come within roughly **6 meters** of one another. When two previously unrelated users cross the proximity threshold, the service generates an event that can result in suggestions to befriend or battle one another.

The service **does not** directly manage battles or notifications — it only emits proximity events. It relies on the **User Management Service** for friend/enemy relationships and publishes events consumed by the **Notification Service**.

### Guild Service

Allows users to create and participate in guilds, maintaining guild identity, membership, roles, and permissions. A guild may have an owner/leader, officers, and ordinary members.

It provides **Guild Chat**, letting members communicate in real time. Messages are associated with a guild and carry timestamps and authors; the service may use **WebSockets** directly for the guild-chat connection.

Guilds act as the social context for **Monster Raids**: members can join an active raid and their primary Tamagotchis become participants in the shared battle. Membership and invitation rules use **User Management Service** for user identity and relationships and **Package Registry Service** for package-registration restrictions.

### Monster Raid Service

Provides a cooperative, clicker-style raid in which members of a guild collectively fight a single powerful monster. A raid has a monster with a large amount of health and a defined duration.

Any eligible guild member may contribute their **primary Tamagotchi** to the raid. Instead of a one-on-one battle, every participating Tamagotchi contributes damage to the same monster. The service maintains the current monster HP, participating users, damage dealt, timestamps, and raid status. Actions may be deliberately simple — players repeatedly attack/click to deal damage, with the amount determined by their primary Tamagotchi's combat properties and any equipped boosts.

When the monster dies, the service distributes rewards (global currency, XP, or other globally managed rewards) to participating users. A raid may also **fail** when its timer expires.

It consults the **Guild Service** for eligible members, the **Tamagotchi Service** for combat properties, and the **User Management Service** to distribute rewards.

### Package Registry Service

Maintains the packages of the apps participating in the ecosystem and acts as the configuration service for package-specific and global game content.

It stores package information (identifier/name, version, description, status, associated developers/moderators) and records which users are registered with which packages.

**Moderators** are privileged users associated with a package, representing its developers. They define the package's local Tamagotchi growth mechanics and statistics. Different packages may use completely different, non-normalized statistics — for example, one package may use *hunger, happiness, tiredness*, while another uses *energy, mood, discipline, creativity*. The service stores the definition and interpretation rules for these statistics, including a statistic's maximum value and thresholds that may produce a combat bonus. The **Battle Service** may consult these definitions to compute package-specific bonuses without requiring all packages to share the same data structure.

**Admins** are globally privileged users who design and schedule Monster Raids. They define monster name, description, sprites, maximum HP, combat statistics, weaknesses, resistances, special properties, raid duration, participant limits, and reward configuration, and may schedule, activate, deactivate, or cancel raids.

### Notification Service

Provides asynchronous communication to users through **Firebase push notifications**. Other services publish events, and this service decides how those events are delivered to the client.

Examples include:

- friend request received,
- nearby player detected,
- battle request received,
- another player used or captured a Tamagotchi,
- guild invitation,
- raid started.

It consumes events published by other services (notably the **User Management Service**, **Map Service**, **Battle Service**, **Guild Service**, and **Monster Raid Service**) and delivers them to the appropriate clients.

## Architecture Diagram

Requests flow from the client through a load balancer to the API Gateway, which fronts the microservices. Each service owns its own database. Synchronous calls (solid arrows) handle request/response between services, while asynchronous events (dotted arrows) are published to the Notification Service, which delivers push notifications via Firebase Cloud Messaging.

![Architecture Diagram](docs/architecture.png)

## Communication Patterns

The architecture uses different communication patterns according to whether a caller needs an immediate result, whether services should remain decoupled, and whether clients require live updates. Solid arrows in the architecture diagram represent synchronous communication, while dashed green arrows represent asynchronous events.

### Client-to-Service Communication

Clients send HTTPS requests through the load balancer and API Gateway. The gateway routes each request to the service that owns the requested functionality. Public APIs use versioned REST endpoints and JSON payloads because REST is supported consistently by both C# and Go and is easy to inspect and test. The trade-off is additional HTTP and JSON overhead compared with a binary protocol.

### Synchronous Service-to-Service Communication

Services use REST over HTTPS with JSON when the caller needs an immediate response before it can continue. Examples include validating a user, checking guild membership, retrieving Tamagotchi combat statistics, and loading package-specific rules.

Synchronous calls keep request and response flows simple, but they also make the caller depend on the availability of the receiving service. Calls therefore use bounded timeouts. Only idempotent requests may be retried automatically, using exponential backoff.

### Asynchronous Event Communication

Services publish JSON domain events through a message queue when the producer does not require an immediate response. This is used for events such as a nearby player being detected, a guild invitation being created, a battle finishing, or a raid starting. Notification Service consumes relevant events and decides whether a Firebase push notification should be sent.

The queue decouples producers from consumers and allows events to be processed even when a consumer is temporarily unavailable. Because an event may be delivered more than once, every event has a unique `eventId` and consumers handle duplicate delivery idempotently. The concrete queue technology will be selected during implementation.

### Real-Time Client Communication

WebSockets provide bidirectional, low-latency communication for Guild Chat. REST remains responsible for creating or retrieving guild resources; WebSockets are used only for live chat messages. Persistent connections require reconnection handling and make horizontal scaling more complex, so they are limited to the feature that needs live bidirectional updates.

### Push Notifications

Only Notification Service communicates directly with Firebase Cloud Messaging. Other services publish domain events instead of calling Firebase themselves. This keeps provider-specific delivery logic outside the business services, at the cost of depending on an external provider whose delivery is not guaranteed to be immediate.

### Data Ownership

Each microservice owns its database and exposes its data only through its API or published events. A service must never read from or write to another service's database directly. Cross-service operations store identifiers rather than duplicating the authoritative entity.

### Service Interaction Matrix

The following interactions correspond to the arrows in the architecture diagram and the real-time Guild Chat requirement.

| Caller / Producer | Receiver / Consumer | Pattern | Purpose |
|---|---|---|---|
| Client | Load Balancer and API Gateway | Synchronous HTTPS | Enter the system and route API requests to the responsible service |
| Client | Guild Service | WebSocket | Send and receive Guild Chat messages in real time |
| Map Service | User Management Service | Synchronous REST | Resolve user identity and friend/enemy relationships for proximity results |
| Map Service | Notification Service | Asynchronous queue event | Report that nearby players were detected |
| User Management Service | Package Registry Service | Synchronous REST | Validate package information associated with a user |
| User Management Service | Notification Service | Asynchronous queue event | Report newly created friend requests |
| Guild Service | User Management Service | Synchronous REST | Validate users, relationships, and permissions used by guild operations |
| Guild Service | Package Registry Service | Synchronous REST | Validate package-related membership information when required |
| Guild Service | Notification Service | Asynchronous queue event | Report newly created guild invitations |
| Monster Raid Service | Guild Service | Synchronous REST | Validate guild membership and raid eligibility |
| Monster Raid Service | User Management Service | Synchronous REST | Credit participating users with global rewards |
| Monster Raid Service | Tamagotchi Service | Synchronous REST | Obtain participating Tamagotchi combat properties |
| Monster Raid Service | Package Registry Service | Synchronous REST | Obtain raid and package-specific combat configuration |
| Monster Raid Service | Notification Service | Asynchronous queue event | Report that a raid started, completed, or failed |
| Battle Service | User Management Service | Synchronous REST | Validate players and apply global currency rewards or losses |
| Battle Service | Tamagotchi Service | Synchronous REST | Obtain combat properties, grant XP, and transfer Tamagotchi ownership |
| Battle Service | Package Registry Service | Synchronous REST | Obtain package-specific combat bonus rules |
| Battle Service | Notification Service | Asynchronous queue event | Report battle invitations and results |
| Tamagotchi Service | Package Registry Service | Synchronous REST | Obtain definitions and interpretation rules for package-local statistics |
| Notification Service | Firebase Cloud Messaging | Provider API | Deliver push notifications to user devices |

### Common Communication Rules

- REST endpoints are versioned under `/api/v1` and use `application/json`.
- Event names include a version suffix, for example `guild.invitation.created.v1`.
- Resource and event identifiers use UUID strings.
- Timestamps use UTC ISO 8601 strings.
- External requests use bearer JWT authentication.
- `X-Correlation-ID` traces one operation across services and events.
- Commands that can be submitted more than once accept an `Idempotency-Key`.
- Services return consistent JSON error objects containing `code`, `message`, and `correlationId`.

## Communication Contract

The communication contract defines the data that callers and services exchange. Endpoint and event payloads use JSON. Fields marked as optional may be omitted; all other fields are required. Unknown fields should be ignored by consumers so that compatible fields can be added later.

### REST Contract Conventions

| Item | Contract |
|---|---|
| Base path | `/api/v1` |
| Content type | `application/json` |
| Authentication | `Authorization: Bearer <JWT>` for external requests |
| Correlation | `X-Correlation-ID: <uuid>`; generated by the gateway when absent |
| Idempotency | `Idempotency-Key: <uuid>` on retriable commands that create side effects |
| Identifier type | UUID encoded as a JSON string |
| Timestamp type | UTC ISO 8601 string, for example `2026-09-07T14:30:00Z` |
| Currency type | Integer amount in the currency's smallest unit |

Successful operations use the following HTTP statuses:

| Status | Meaning |
|---:|---|
| `200 OK` | Resource returned or command completed |
| `201 Created` | New resource created |
| `202 Accepted` | Command accepted for asynchronous processing |
| `204 No Content` | Command completed without a response body |

Errors use an appropriate `4xx` or `5xx` status and the following common body:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource does not exist.",
    "correlationId": "b991f2c1-44db-4c41-bc00-24b72fe93e93",
    "details": []
  }
}
```

Common error statuses are `400` for an invalid request, `401` for missing or invalid authentication, `403` for insufficient permissions, `404` for a missing resource, `409` for a state conflict, `422` for a rejected domain operation, `429` for rate limiting, and `503` when a required dependency is unavailable.

### Asynchronous Event Contract

Every event sent through the queue uses the following envelope:

```json
{
  "eventId": "44b37851-48e1-480e-a668-7f0e02f85c24",
  "eventType": "guild.invitation.created.v1",
  "eventVersion": 1,
  "occurredAt": "2026-09-07T14:30:00Z",
  "producer": "guild-service",
  "correlationId": "b991f2c1-44db-4c41-bc00-24b72fe93e93",
  "data": {}
}
```

| Field | Type | Meaning |
|---|---|---|
| `eventId` | UUID string | Unique event identifier used for deduplication |
| `eventType` | String | Stable event name including the version suffix |
| `eventVersion` | Integer | Schema version of the event |
| `occurredAt` | UTC timestamp | Time at which the business event occurred |
| `producer` | String | Service that published the event |
| `correlationId` | UUID string | Identifier connecting the event to the originating operation |
| `data` | Object | Event-specific payload defined in the event catalog |

### Data Ownership and Storage

| Service | Storage from the architecture | Authoritative data | Reason and trade-off |
|---|---|---|---|
| User Management Service | PostgreSQL | Accounts, credentials, profiles, friends/enemies, global and local balances | Transactions and constraints protect identity and balances; the relational schema is less flexible for package-specific data. |
| Map Service | Redis | Latest user coordinates and location timestamps | Fast access and expiration fit temporary locations; location history is deliberately not durable. |
| Notification Service | Redis | Device tokens, notification preferences, delivery and deduplication state | Fast TTL-based deduplication supports event delivery; it does not provide permanent notification history. |
| Guild Service | PostgreSQL and MongoDB | Guilds, memberships, roles and permissions in PostgreSQL; Guild Chat messages in MongoDB | Relational constraints protect membership while MongoDB supports flexible chat documents; two databases increase operational complexity. |
| Monster Raid Service | Redis | Active raid state, participants, damage, timers and recent results | Low-latency atomic updates suit a clicker raid; finished results are retained only for a configured period. |
| Battle Service | Redis | Active battle state, turns, health and recent results | Low-latency turn updates suit short-lived battles; permanent battle history is outside the current design. |
| Tamagotchi Service | MongoDB | Tamagotchi identity, owner, combat type, level, sprite references and package-local health statistics | Documents support non-normalized package-specific statistics; ownership invariants must be enforced by the service. |
| Package Registry Service | MongoDB | Package definitions, user-package registrations, moderators, statistic rules and raid configurations | Flexible documents support different package rules; cross-document consistency is handled in application logic. |

Cross-service references use resource identifiers rather than direct database access. APIs and events may include the data snapshot required to complete an operation. Package Registry Service is the authority for package definitions and registrations; User Management Service keeps only the package references needed in a user profile. Tamagotchi Service remains the authority for Tamagotchi ownership, including transfers after battles.

### Service API Contracts

#### User Management Service

User Management Service owns user identity, authentication, social relationships, and currency balances. Passwords are accepted only by registration and authentication endpoints and are never returned. Internal balance commands require an authenticated service identity in addition to the common correlation and idempotency headers.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `POST /api/v1/users` | Client | `CreateUserRequest` | `201 UserResponse` | `400`, `409 USERNAME_OR_EMAIL_TAKEN`, `503 PACKAGE_REGISTRY_UNAVAILABLE` |
| `POST /api/v1/auth/sessions` | Client | `LoginRequest` | `200 AuthSessionResponse` | `400`, `401 INVALID_CREDENTIALS` |
| `POST /api/v1/auth/sessions/refresh` | Client | `RefreshSessionRequest` | `200 AuthSessionResponse` | `401 INVALID_REFRESH_TOKEN` |
| `DELETE /api/v1/auth/sessions/current` | Client | None | `204` | `401 INVALID_TOKEN` |
| `GET /api/v1/users/{userId}` | Client or internal service | None | `200 UserResponse` | `401`, `403`, `404 USER_NOT_FOUND` |
| `PATCH /api/v1/users/{userId}` | Account owner | `UpdateUserRequest` | `200 UserResponse` | `400`, `401`, `403`, `404`, `409 EMAIL_TAKEN` |
| `GET /api/v1/users/{userId}/relationships/{otherUserId}` | Client, Map, or Guild Service | None | `200 RelationshipResponse` | `401`, `403`, `404 USER_NOT_FOUND` |
| `POST /api/v1/users/{userId}/friend-requests` | Client | `CreateFriendRequest` | `201 FriendRequestResponse` | `400`, `403`, `404`, `409 RELATIONSHIP_EXISTS` |
| `POST /api/v1/users/{userId}/friend-requests/{requestId}/responses` | Request recipient | `RespondToFriendRequest` | `200 FriendRequestResponse` | `400`, `403`, `404`, `409 REQUEST_ALREADY_RESOLVED` |
| `PUT /api/v1/users/{userId}/enemies/{enemyUserId}` | Account owner | None | `204` | `403`, `404`, `409 RELATIONSHIP_CONFLICT` |
| `DELETE /api/v1/users/{userId}/enemies/{enemyUserId}` | Account owner | None | `204` | `403`, `404` |
| `GET /api/v1/users/{userId}/balances` | Account owner, Battle, or Monster Raid Service | None | `200 BalanceResponse` | `403`, `404 USER_NOT_FOUND` |
| `POST /api/v1/users/{userId}/balance-transactions` | Battle or Monster Raid Service | `BalanceTransactionRequest` | `200 BalanceTransactionResponse` | `400`, `403`, `404`, `422 INSUFFICIENT_BALANCE` |
| `GET /api/v1/users/{userId}/packages` | Account owner or internal service | None | `200 PackageReference[]` | `403`, `404 USER_NOT_FOUND` |
| `POST /api/v1/users/{userId}/packages/{packageId}` | Account owner | None | `201 PackageReference` | `403`, `404 USER_OR_PACKAGE_NOT_FOUND`, `409 PACKAGE_ALREADY_REGISTERED`, `503 PACKAGE_REGISTRY_UNAVAILABLE` |

##### Payload Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateUserRequest` | `username` | String, 3-32 characters | Yes | Public username |
| `CreateUserRequest` | `email` | Email string | Yes | Unique account email |
| `CreateUserRequest` | `password` | String, 8-72 characters | Yes | Plain password transported only over HTTPS |
| `CreateUserRequest` | `initialPackageId` | UUID string | Yes | Package selected during registration |
| `UpdateUserRequest` | `username` | String, 3-32 characters | No | New public username |
| `UpdateUserRequest` | `email` | Email string | No | New unique email address |
| `LoginRequest` | `email` | Email string | Yes | Account email |
| `LoginRequest` | `password` | String | Yes | Account password |
| `RefreshSessionRequest` | `refreshToken` | String | Yes | Previously issued refresh token |
| `AuthSessionResponse` | `accessToken` | String | Yes | Bearer JWT used for authenticated requests |
| `AuthSessionResponse` | `refreshToken` | String | Yes | Token used to renew the session |
| `AuthSessionResponse` | `expiresAt` | UTC timestamp | Yes | Access-token expiration time |
| `UserResponse` | `userId` | UUID string | Yes | Global user identifier |
| `UserResponse` | `username` | String | Yes | Public username |
| `UserResponse` | `email` | Email string | Yes | Account email, visible only to the owner or authorized services |
| `UserResponse` | `packageIds` | Array of UUID strings | Yes | References to registered packages |
| `UserResponse` | `createdAt` | UTC timestamp | Yes | Account creation time |
| `RelationshipResponse` | `userId` | UUID string | Yes | First user in the relationship query |
| `RelationshipResponse` | `otherUserId` | UUID string | Yes | Second user in the relationship query |
| `RelationshipResponse` | `relationship` | `FRIEND`, `ENEMY`, or `NONE` | Yes | Current relationship classification |
| `CreateFriendRequest` | `targetUserId` | UUID string | Yes | User who should receive the request |
| `RespondToFriendRequest` | `decision` | `ACCEPT` or `REJECT` | Yes | Recipient's decision |
| `FriendRequestResponse` | `requestId` | UUID string | Yes | Friend-request identifier |
| `FriendRequestResponse` | `senderUserId` | UUID string | Yes | User who sent the request |
| `FriendRequestResponse` | `recipientUserId` | UUID string | Yes | User who receives the request |
| `FriendRequestResponse` | `status` | `PENDING`, `ACCEPTED`, or `REJECTED` | Yes | Current request state |
| `FriendRequestResponse` | `createdAt` | UTC timestamp | Yes | Request creation time |
| `BalanceResponse` | `userId` | UUID string | Yes | Balance owner |
| `BalanceResponse` | `globalBalance` | Integer | Yes | Global currency in its smallest unit |
| `BalanceResponse` | `localBalances` | Array of `LocalBalance` | Yes | One local balance per registered package |
| `LocalBalance` | `packageId` | UUID string | Yes | Package defining the local currency |
| `LocalBalance` | `balance` | Integer | Yes | Local currency in its smallest unit |
| `BalanceTransactionRequest` | `currency` | `GLOBAL` or `LOCAL` | Yes | Balance that should be changed |
| `BalanceTransactionRequest` | `packageId` | UUID string | Conditional | Required when `currency` is `LOCAL` |
| `BalanceTransactionRequest` | `amount` | Non-zero integer | Yes | Positive for credit and negative for debit |
| `BalanceTransactionRequest` | `reason` | `BATTLE_REWARD`, `BATTLE_LOSS`, `RAID_REWARD`, or `ADMIN_ADJUSTMENT` | Yes | Business reason for the balance change |
| `BalanceTransactionRequest` | `referenceId` | UUID string | Yes | Battle, raid, or administrative operation identifier |
| `BalanceTransactionResponse` | `transactionId` | UUID string | Yes | Recorded transaction identifier |
| `BalanceTransactionResponse` | `resultingBalance` | Integer | Yes | Balance after applying the transaction |
| `BalanceTransactionResponse` | `processedAt` | UTC timestamp | Yes | Processing time |
| `PackageReference` | `packageId` | UUID string | Yes | Registered package identifier |
| `PackageReference` | `registeredAt` | UTC timestamp | Yes | Time at which the user registered with the package |

##### Published Queue Event

`user.friend-request.created.v1` is published after a friend request is stored successfully. Notification Service consumes it to notify the recipient.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `requestId` | UUID string | Yes | Friend-request identifier |
| `senderUserId` | UUID string | Yes | User who sent the request |
| `recipientUserId` | UUID string | Yes | User who should be notified |
| `createdAt` | UTC timestamp | Yes | Request creation time |

##### Outbound Dependencies

| Receiver | Operation | Reason |
|---|---|---|
| Package Registry Service | Retrieve a package by `packageId` | Validate that a package exists and is active |
| Package Registry Service | Register `userId` with `packageId` | Make Package Registry the authority for the registration |

#### Package Registry Service

Package Registry Service owns package metadata, package membership, package-specific Tamagotchi statistic definitions, and Monster Raid configurations and schedules. Package moderators manage their own package configuration, while globally privileged admins manage raid configuration and scheduling.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /api/v1/packages?status={status}&cursor={cursor}&limit={limit}` | Client or internal service | Query parameters | `200 PackagePageResponse` | `400 INVALID_QUERY` |
| `POST /api/v1/packages` | Developer or admin | `CreatePackageRequest` | `201 PackageResponse` | `400`, `403`, `409 PACKAGE_NAME_TAKEN` |
| `GET /api/v1/packages/{packageId}` | Client or internal service | None | `200 PackageResponse` | `404 PACKAGE_NOT_FOUND` |
| `PATCH /api/v1/packages/{packageId}` | Package moderator or admin | `UpdatePackageRequest` | `200 PackageResponse` | `400`, `403`, `404`, `409 VERSION_CONFLICT` |
| `POST /api/v1/packages/{packageId}/moderators` | Package developer or admin | `AddModeratorRequest` | `201 ModeratorResponse` | `403`, `404`, `409 MODERATOR_EXISTS` |
| `DELETE /api/v1/packages/{packageId}/moderators/{userId}` | Package developer or admin | None | `204` | `403`, `404 MODERATOR_NOT_FOUND` |
| `POST /api/v1/packages/{packageId}/registrations` | User Management Service | `RegisterUserPackageRequest` | `201 PackageRegistrationResponse` | `400`, `403`, `404`, `409 PACKAGE_ALREADY_REGISTERED` |
| `GET /api/v1/packages/{packageId}/registrations/{userId}` | User Management or Guild Service | None | `200 PackageRegistrationResponse` | `403`, `404 REGISTRATION_NOT_FOUND` |
| `GET /api/v1/package-registrations?userId={userId}` | User Management Service | Query parameter | `200 PackageRegistrationResponse[]` | `400`, `403` |
| `PUT /api/v1/packages/{packageId}/stat-definitions` | Package moderator | `ReplaceStatDefinitionsRequest` | `200 StatDefinitionResponse[]` | `400`, `403`, `404 PACKAGE_NOT_FOUND`, `422 INVALID_STAT_RULE` |
| `GET /api/v1/packages/{packageId}/stat-definitions` | Tamagotchi, Battle, or Monster Raid Service | None | `200 StatDefinitionResponse[]` | `403`, `404 PACKAGE_NOT_FOUND` |
| `PUT /api/v1/packages/{packageId}/battle-boosts` | Package moderator | `ReplaceBattleBoostsRequest` | `200 BattleBoostResponse[]` | `400`, `403`, `404 PACKAGE_NOT_FOUND`, `422 INVALID_BOOST` |
| `GET /api/v1/packages/{packageId}/battle-boosts` | Client or Battle Service | None | `200 BattleBoostResponse[]` | `403`, `404 PACKAGE_NOT_FOUND` |
| `GET /api/v1/packages/{packageId}/battle-boosts/{boostKey}` | Battle Service | None | `200 BattleBoostResponse` | `403`, `404 BOOST_NOT_FOUND` |
| `GET /api/v1/raid-configurations?cursor={cursor}&limit={limit}` | Client, admin, or Monster Raid Service | Query parameters | `200 RaidConfigurationPageResponse` | `400 INVALID_QUERY` |
| `POST /api/v1/raid-configurations` | Admin | `CreateRaidConfigurationRequest` | `201 RaidConfigurationResponse` | `400`, `403`, `422 INVALID_RAID_CONFIGURATION` |
| `GET /api/v1/raid-configurations/{raidConfigurationId}` | Client or Monster Raid Service | None | `200 RaidConfigurationResponse` | `404 RAID_CONFIGURATION_NOT_FOUND` |
| `PATCH /api/v1/raid-configurations/{raidConfigurationId}` | Admin | `UpdateRaidConfigurationRequest` | `200 RaidConfigurationResponse` | `400`, `403`, `404`, `409 ACTIVE_CONFIGURATION_LOCKED` |
| `POST /api/v1/raid-configurations/{raidConfigurationId}/schedules` | Admin | `CreateRaidScheduleRequest` | `201 RaidScheduleResponse` | `400`, `403`, `404`, `409 SCHEDULE_CONFLICT` |
| `GET /api/v1/raid-schedules?status={status}&at={timestamp}` | Monster Raid Service or admin | Query parameters | `200 RaidScheduleResponse[]` | `400 INVALID_QUERY`, `403` |
| `GET /api/v1/raid-schedules/{scheduleId}` | Monster Raid Service or admin | None | `200 RaidScheduleResponse` | `403`, `404 RAID_SCHEDULE_NOT_FOUND` |
| `POST /api/v1/raid-schedules/{scheduleId}/activate` | Admin | None | `200 RaidScheduleResponse` | `403`, `404`, `409 INVALID_SCHEDULE_STATE` |
| `POST /api/v1/raid-schedules/{scheduleId}/deactivate` | Admin | None | `200 RaidScheduleResponse` | `403`, `404`, `409 INVALID_SCHEDULE_STATE` |
| `POST /api/v1/raid-schedules/{scheduleId}/cancel` | Admin | None | `200 RaidScheduleResponse` | `403`, `404`, `409 INVALID_SCHEDULE_STATE` |

##### Package and Registration Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreatePackageRequest` | `name` | String, 1-100 characters | Yes | Unique package name |
| `CreatePackageRequest` | `version` | Semantic-version string | Yes | Initial package version |
| `CreatePackageRequest` | `description` | String, maximum 2,000 characters | Yes | Package description |
| `CreatePackageRequest` | `developerIds` | Array of UUID strings | Yes | Users responsible for developing the package |
| `UpdatePackageRequest` | `version` | Semantic-version string | No | New package version |
| `UpdatePackageRequest` | `description` | String, maximum 2,000 characters | No | Updated description |
| `UpdatePackageRequest` | `status` | `DRAFT`, `ACTIVE`, or `INACTIVE` | No | Package availability |
| `PackageResponse` | `packageId` | UUID string | Yes | Package identifier |
| `PackageResponse` | `name` | String | Yes | Package name |
| `PackageResponse` | `version` | Semantic-version string | Yes | Current version |
| `PackageResponse` | `description` | String | Yes | Package description |
| `PackageResponse` | `status` | `DRAFT`, `ACTIVE`, or `INACTIVE` | Yes | Current package state |
| `PackageResponse` | `developerIds` | Array of UUID strings | Yes | Associated developers |
| `PackageResponse` | `moderatorIds` | Array of UUID strings | Yes | Associated moderators |
| `PackageResponse` | `createdAt` | UTC timestamp | Yes | Creation time |
| `PackageResponse` | `updatedAt` | UTC timestamp | Yes | Last update time |
| `PackagePageResponse` | `items` | Array of `PackageResponse` | Yes | Packages in the current page |
| `PackagePageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `AddModeratorRequest` | `userId` | UUID string | Yes | User who receives moderator privileges |
| `ModeratorResponse` | `packageId` | UUID string | Yes | Associated package |
| `ModeratorResponse` | `userId` | UUID string | Yes | Moderator user identifier |
| `ModeratorResponse` | `assignedAt` | UTC timestamp | Yes | Assignment time |
| `RegisterUserPackageRequest` | `userId` | UUID string | Yes | User being registered |
| `PackageRegistrationResponse` | `packageId` | UUID string | Yes | Registered package |
| `PackageRegistrationResponse` | `userId` | UUID string | Yes | Registered user |
| `PackageRegistrationResponse` | `registeredAt` | UTC timestamp | Yes | Registration time |

##### Statistic Definition Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `ReplaceStatDefinitionsRequest` | `definitions` | Array of `StatDefinition` | Yes | Complete replacement for the package's statistic definitions |
| `StatDefinition` | `key` | Lowercase string | Yes | Stable machine-readable statistic name, such as `hunger` |
| `StatDefinition` | `displayName` | String | Yes | Human-readable statistic name |
| `StatDefinition` | `valueType` | `INTEGER`, `DECIMAL`, or `BOOLEAN` | Yes | Data type accepted for the statistic |
| `StatDefinition` | `minimumValue` | Number | Conditional | Minimum for numeric statistics |
| `StatDefinition` | `maximumValue` | Number | Conditional | Maximum for numeric statistics |
| `StatDefinition` | `combatBonusRules` | Array of `CombatBonusRule` | Yes | Rules for translating local statistics into combat bonuses |
| `CombatBonusRule` | `operator` | `LT`, `LTE`, `GT`, `GTE`, or `BETWEEN` | Yes | Comparison applied to the statistic |
| `CombatBonusRule` | `threshold` | Number or two-number array | Yes | Value or range used by the comparison |
| `CombatBonusRule` | `bonusType` | `ATTACK`, `DEFENSE`, or `HEALTH` | Yes | Combat property affected by the rule |
| `CombatBonusRule` | `modifier` | Decimal number | Yes | Bonus added when the condition matches |
| `StatDefinitionResponse` | `packageId` | UUID string | Yes | Package owning the definition |
| `StatDefinitionResponse` | `definition` | `StatDefinition` | Yes | Stored statistic definition |
| `StatDefinitionResponse` | `updatedAt` | UTC timestamp | Yes | Last definition update time |

##### Battle Boost Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `ReplaceBattleBoostsRequest` | `boosts` | Array of `BattleBoostDefinition` | Yes | Complete replacement for the package's battle boosts |
| `BattleBoostDefinition` | `key` | Lowercase string | Yes | Stable boost identifier within the package |
| `BattleBoostDefinition` | `displayName` | String | Yes | Human-readable boost name |
| `BattleBoostDefinition` | `affectedStat` | `ATTACK`, `DEFENSE`, or `HEALTH` | Yes | Combat property modified by the boost |
| `BattleBoostDefinition` | `modifier` | Decimal number | Yes | Value added while the boost is active |
| `BattleBoostDefinition` | `maxUsesPerBattle` | Positive integer | Yes | Maximum number of uses in one battle |
| `BattleBoostResponse` | `packageId` | UUID string | Yes | Package owning the boost |
| `BattleBoostResponse` | `definition` | `BattleBoostDefinition` | Yes | Stored boost definition |
| `BattleBoostResponse` | `updatedAt` | UTC timestamp | Yes | Last update time |

##### Raid Configuration and Schedule Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateRaidConfigurationRequest` | `name` | String | Yes | Monster name |
| `CreateRaidConfigurationRequest` | `description` | String | Yes | Monster and raid description |
| `CreateRaidConfigurationRequest` | `spriteUrl` | URL string | Yes | Monster sprite location |
| `CreateRaidConfigurationRequest` | `maximumHp` | Positive integer | Yes | Starting monster health |
| `CreateRaidConfigurationRequest` | `combatStats` | `RaidCombatStats` | Yes | Attack and defense properties |
| `CreateRaidConfigurationRequest` | `weaknesses` | Array of combat-type strings | Yes | Types that deal increased damage |
| `CreateRaidConfigurationRequest` | `resistances` | Array of combat-type strings | Yes | Types that deal reduced damage |
| `CreateRaidConfigurationRequest` | `specialProperties` | JSON object | Yes | Extensible special raid behavior |
| `CreateRaidConfigurationRequest` | `durationSeconds` | Positive integer | Yes | Maximum raid duration |
| `CreateRaidConfigurationRequest` | `participantLimit` | Positive integer | Yes | Maximum number of participants |
| `CreateRaidConfigurationRequest` | `rewards` | `RaidRewardConfiguration` | Yes | Reward rules for a successful raid |
| `UpdateRaidConfigurationRequest` | Any create field | Same as create field | No | Field to update before activation |
| `RaidCombatStats` | `attack` | Non-negative integer | Yes | Monster attack value |
| `RaidCombatStats` | `defense` | Non-negative integer | Yes | Monster defense value |
| `RaidRewardConfiguration` | `globalCurrency` | Non-negative integer | Yes | Global currency awarded per eligible participant |
| `RaidRewardConfiguration` | `xp` | Non-negative integer | Yes | XP awarded per eligible participant |
| `RaidRewardConfiguration` | `otherRewards` | Array of JSON objects | Yes | Optional globally managed rewards |
| `RaidConfigurationResponse` | `raidConfigurationId` | UUID string | Yes | Raid configuration identifier |
| `RaidConfigurationResponse` | All create fields | Corresponding types | Yes | Stored configuration values |
| `RaidConfigurationResponse` | `createdAt` | UTC timestamp | Yes | Creation time |
| `RaidConfigurationResponse` | `updatedAt` | UTC timestamp | Yes | Last update time |
| `RaidConfigurationPageResponse` | `items` | Array of `RaidConfigurationResponse` | Yes | Configurations in the current page |
| `RaidConfigurationPageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `CreateRaidScheduleRequest` | `startsAt` | Future UTC timestamp | Yes | Scheduled activation time |
| `CreateRaidScheduleRequest` | `endsAt` | UTC timestamp | Yes | Scheduled end time |
| `RaidScheduleResponse` | `scheduleId` | UUID string | Yes | Schedule identifier |
| `RaidScheduleResponse` | `raidConfigurationId` | UUID string | Yes | Configuration used by the scheduled raid |
| `RaidScheduleResponse` | `startsAt` | UTC timestamp | Yes | Scheduled start time |
| `RaidScheduleResponse` | `endsAt` | UTC timestamp | Yes | Scheduled end time |
| `RaidScheduleResponse` | `status` | `SCHEDULED`, `ACTIVE`, `INACTIVE`, `CANCELLED`, or `COMPLETED` | Yes | Current schedule state |
| `RaidScheduleResponse` | `createdByAdminId` | UUID string | Yes | Admin who created the schedule |

##### Outbound and Inbound Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Inbound | User Management Service | Read package and create/read registration | Validate and record a user's package membership |
| Inbound | Tamagotchi Service | Read statistic definitions | Validate package-local Tamagotchi statistics |
| Inbound | Battle Service | Read statistic and battle-boost definitions | Calculate package-specific combat bonuses |
| Inbound | Monster Raid Service | Read statistic definitions, raid configurations, and active schedules | Calculate combat bonuses and initialize scheduled raids |
| Inbound | Guild Service | Read a package registration when package membership affects a guild rule | Enforce the configured membership rule |

#### Guild Service

Guild Service owns guild identity, membership, roles, permissions, and Guild Chat. Relational guild data is stored in PostgreSQL, while chat messages are stored in MongoDB. The service uses User Management Service for user identity and relationships and Package Registry Service only when a guild restricts membership to a package.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /api/v1/guilds?cursor={cursor}&limit={limit}` | Client | Query parameters | `200 GuildPageResponse` | `400 INVALID_QUERY` |
| `POST /api/v1/guilds` | Client | `CreateGuildRequest` | `201 GuildResponse` | `400`, `403`, `404 PACKAGE_NOT_FOUND`, `409 GUILD_NAME_TAKEN` |
| `GET /api/v1/guilds/{guildId}` | Client or Monster Raid Service | None | `200 GuildResponse` | `404 GUILD_NOT_FOUND` |
| `PATCH /api/v1/guilds/{guildId}` | Guild owner | `UpdateGuildRequest` | `200 GuildResponse` | `400`, `403`, `404`, `409 GUILD_NAME_TAKEN` |
| `DELETE /api/v1/guilds/{guildId}` | Guild owner | None | `204` | `403`, `404`, `409 ACTIVE_RAID_EXISTS` |
| `GET /api/v1/users/{userId}/guilds` | Account owner or internal service | None | `200 GuildResponse[]` | `403`, `404 USER_NOT_FOUND` |
| `GET /api/v1/guilds/{guildId}/members?cursor={cursor}&limit={limit}` | Guild member or Monster Raid Service | Query parameters | `200 GuildMemberPageResponse` | `400`, `403`, `404 GUILD_NOT_FOUND` |
| `GET /api/v1/guilds/{guildId}/members/{userId}` | Guild member or Monster Raid Service | None | `200 GuildMemberResponse` | `403`, `404 MEMBERSHIP_NOT_FOUND` |
| `PATCH /api/v1/guilds/{guildId}/members/{userId}` | Guild owner | `UpdateGuildMemberRequest` | `200 GuildMemberResponse` | `400`, `403`, `404`, `409 INVALID_ROLE_CHANGE` |
| `DELETE /api/v1/guilds/{guildId}/members/{userId}` | Member, officer, or owner | None | `204` | `403`, `404`, `409 OWNER_CANNOT_LEAVE` |
| `POST /api/v1/guilds/{guildId}/ownership-transfers` | Guild owner | `TransferGuildOwnershipRequest` | `200 GuildResponse` | `400`, `403`, `404`, `409 INVALID_NEW_OWNER` |
| `POST /api/v1/guilds/{guildId}/invitations` | Guild owner or officer | `CreateGuildInvitationRequest` | `201 GuildInvitationResponse` | `400`, `403`, `404`, `409 INVITATION_OR_MEMBERSHIP_EXISTS`, `422 MEMBERSHIP_RULE_NOT_SATISFIED` |
| `GET /api/v1/guilds/{guildId}/invitations?status={status}` | Guild owner or officer | Query parameter | `200 GuildInvitationResponse[]` | `400`, `403`, `404 GUILD_NOT_FOUND` |
| `GET /api/v1/users/{userId}/guild-invitations?status={status}` | Invitation recipient | Query parameter | `200 GuildInvitationResponse[]` | `400`, `403`, `404 USER_NOT_FOUND` |
| `POST /api/v1/guilds/{guildId}/invitations/{invitationId}/accept` | Invitation recipient | None | `200 GuildMemberResponse` | `403`, `404`, `409 INVITATION_ALREADY_RESOLVED`, `422 MEMBERSHIP_RULE_NOT_SATISFIED` |
| `POST /api/v1/guilds/{guildId}/invitations/{invitationId}/reject` | Invitation recipient | None | `200 GuildInvitationResponse` | `403`, `404`, `409 INVITATION_ALREADY_RESOLVED` |
| `GET /api/v1/guilds/{guildId}/messages?before={messageId}&limit={limit}` | Guild member | Query parameters | `200 GuildMessagePageResponse` | `400`, `403`, `404 GUILD_NOT_FOUND` |

##### Guild and Membership Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateGuildRequest` | `name` | String, 3-80 characters | Yes | Unique guild name |
| `CreateGuildRequest` | `description` | String, maximum 1,000 characters | Yes | Public guild description |
| `CreateGuildRequest` | `requiredPackageId` | UUID string | No | Package required for membership, if the guild is restricted |
| `UpdateGuildRequest` | `name` | String, 3-80 characters | No | Updated guild name |
| `UpdateGuildRequest` | `description` | String, maximum 1,000 characters | No | Updated description |
| `UpdateGuildRequest` | `requiredPackageId` | UUID string or `null` | No | Add, replace, or remove the package restriction |
| `GuildResponse` | `guildId` | UUID string | Yes | Guild identifier |
| `GuildResponse` | `name` | String | Yes | Guild name |
| `GuildResponse` | `description` | String | Yes | Guild description |
| `GuildResponse` | `ownerId` | UUID string | Yes | Current guild owner |
| `GuildResponse` | `requiredPackageId` | UUID string or `null` | Yes | Required package, if configured |
| `GuildResponse` | `memberCount` | Non-negative integer | Yes | Current number of members |
| `GuildResponse` | `createdAt` | UTC timestamp | Yes | Guild creation time |
| `GuildResponse` | `updatedAt` | UTC timestamp | Yes | Last guild update time |
| `GuildPageResponse` | `items` | Array of `GuildResponse` | Yes | Guilds in the current page |
| `GuildPageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `GuildMemberResponse` | `guildId` | UUID string | Yes | Guild containing the member |
| `GuildMemberResponse` | `userId` | UUID string | Yes | Member's user identifier |
| `GuildMemberResponse` | `role` | `OWNER`, `OFFICER`, or `MEMBER` | Yes | Member's guild role |
| `GuildMemberResponse` | `joinedAt` | UTC timestamp | Yes | Membership creation time |
| `GuildMemberPageResponse` | `items` | Array of `GuildMemberResponse` | Yes | Members in the current page |
| `GuildMemberPageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `UpdateGuildMemberRequest` | `role` | `OFFICER` or `MEMBER` | Yes | New role; ownership uses the separate transfer endpoint |
| `TransferGuildOwnershipRequest` | `newOwnerId` | UUID string | Yes | Existing member who becomes the owner |

##### Invitation Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateGuildInvitationRequest` | `inviteeUserId` | UUID string | Yes | User invited to the guild |
| `GuildInvitationResponse` | `invitationId` | UUID string | Yes | Invitation identifier |
| `GuildInvitationResponse` | `guildId` | UUID string | Yes | Target guild |
| `GuildInvitationResponse` | `inviterUserId` | UUID string | Yes | Owner or officer who sent the invitation |
| `GuildInvitationResponse` | `inviteeUserId` | UUID string | Yes | User receiving the invitation |
| `GuildInvitationResponse` | `status` | `PENDING`, `ACCEPTED`, `REJECTED`, `EXPIRED`, or `CANCELLED` | Yes | Current invitation state |
| `GuildInvitationResponse` | `createdAt` | UTC timestamp | Yes | Invitation creation time |
| `GuildInvitationResponse` | `expiresAt` | UTC timestamp | Yes | Time after which it can no longer be accepted |

##### Guild Chat REST Schema

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `GuildMessageResponse` | `messageId` | UUID string | Yes | Stored message identifier |
| `GuildMessageResponse` | `guildId` | UUID string | Yes | Guild chat containing the message |
| `GuildMessageResponse` | `authorUserId` | UUID string | Yes | Message author |
| `GuildMessageResponse` | `content` | String, 1-2,000 characters | Yes | Message text |
| `GuildMessageResponse` | `sentAt` | UTC timestamp | Yes | Message creation time |
| `GuildMessagePageResponse` | `items` | Array of `GuildMessageResponse` | Yes | Messages ordered from newest to oldest |
| `GuildMessagePageResponse` | `nextCursor` | String or `null` | Yes | Cursor for older messages |

##### Guild Chat WebSocket Contract

Guild members connect to `/ws/v1/guilds/{guildId}/chat` using a bearer JWT during the connection handshake. The service rejects unauthenticated users and users who are not active members of the guild.

The client sends:

```json
{
  "type": "guild.chat.message.send.v1",
  "clientMessageId": "a30b3bd2-3c74-4fe1-9f53-c67ea72171db",
  "content": "Ready for the raid?"
}
```

After storing the message, the server broadcasts:

```json
{
  "type": "guild.chat.message.created.v1",
  "clientMessageId": "a30b3bd2-3c74-4fe1-9f53-c67ea72171db",
  "messageId": "197a02a7-253e-4ec6-a4ee-b5d41c6e3142",
  "guildId": "813e29b1-4471-4111-9c51-c8f293fd7ab6",
  "authorUserId": "ad01bf52-d4d8-47a2-8b2f-d71757a9ae75",
  "content": "Ready for the raid?",
  "sentAt": "2026-09-07T14:30:00Z"
}
```

If a message cannot be processed, the sender receives `guild.chat.error.v1` with `clientMessageId`, an error `code`, a human-readable `message`, and `correlationId`. Reusing a `clientMessageId` returns the previously stored message instead of creating a duplicate.

##### Published Queue Event

`guild.invitation.created.v1` is published after an invitation is stored successfully. Notification Service consumes it to notify the invited user.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `invitationId` | UUID string | Yes | Invitation identifier |
| `guildId` | UUID string | Yes | Guild sending the invitation |
| `guildName` | String | Yes | Name displayed in the notification |
| `inviterUserId` | UUID string | Yes | User who sent the invitation |
| `inviteeUserId` | UUID string | Yes | User who should be notified |
| `expiresAt` | UTC timestamp | Yes | Invitation expiration time |

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Outbound | User Management Service | Read users and relationships | Validate inviter, invitee, and relationship rules |
| Outbound | Package Registry Service | Read package and user-package registration | Enforce an optional package membership restriction |
| Inbound | Monster Raid Service | Read guild and membership | Validate whether a user may participate in a guild raid |
| Outbound | Notification Service through Queue | Publish guild invitation event | Notify the invited user asynchronously |

#### Tamagotchi Service

Tamagotchi Service owns every Tamagotchi and its current owner, role, combat type, level, XP, sprite reference, and package-local health statistics. A secondary Tamagotchi is a reference to the original entity after an ownership transfer; the service never creates a duplicate of it.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /api/v1/tamagotchi-combat-types` | Client or internal service | None | `200 CombatTypeResponse[]` | None |
| `POST /api/v1/tamagotchis` | Account owner or package client | `CreateTamagotchiRequest` | `201 TamagotchiResponse` | `400`, `403`, `404 PACKAGE_NOT_FOUND`, `409 PRIMARY_TAMAGOTCHI_EXISTS`, `422 INVALID_LOCAL_STATS` |
| `GET /api/v1/tamagotchis/{tamagotchiId}` | Account owner or internal service | None | `200 TamagotchiResponse` | `403`, `404 TAMAGOTCHI_NOT_FOUND` |
| `PATCH /api/v1/tamagotchis/{tamagotchiId}` | Account owner | `UpdateTamagotchiRequest` | `200 TamagotchiResponse` | `400`, `403`, `404` |
| `GET /api/v1/users/{userId}/tamagotchis?role={role}` | Account owner or internal service | Query parameter | `200 TamagotchiResponse[]` | `400 INVALID_ROLE`, `403`, `404 USER_TAMAGOTCHIS_NOT_FOUND` |
| `GET /api/v1/users/{userId}/primary-tamagotchi` | Account owner, Battle, or Monster Raid Service | None | `200 TamagotchiResponse` | `403`, `404 PRIMARY_TAMAGOTCHI_NOT_FOUND` |
| `PUT /api/v1/users/{userId}/primary-tamagotchi` | Account owner | `SetPrimaryTamagotchiRequest` | `200 TamagotchiResponse` | `400`, `403`, `404`, `409 TAMAGOTCHI_NOT_OWNED` |
| `PATCH /api/v1/tamagotchis/{tamagotchiId}/health-stats` | Account owner or package client | `UpdateHealthStatsRequest` | `200 TamagotchiResponse` | `400`, `403`, `404`, `422 INVALID_LOCAL_STATS`, `503 PACKAGE_REGISTRY_UNAVAILABLE` |
| `GET /api/v1/tamagotchis/{tamagotchiId}/combat-profile` | Battle or Monster Raid Service | None | `200 CombatProfileResponse` | `403`, `404 TAMAGOTCHI_NOT_FOUND`, `422 TAMAGOTCHI_UNAVAILABLE` |
| `POST /api/v1/tamagotchis/{tamagotchiId}/xp-grants` | Battle or Monster Raid Service | `GrantXpRequest` | `200 GrantXpResponse` | `400`, `403`, `404`, `409 XP_ALREADY_GRANTED` |
| `POST /api/v1/tamagotchi-ownership-transfers` | Battle Service | `TransferTamagotchiRequest` | `200 OwnershipTransferResponse` | `400`, `403`, `404`, `409 OWNERSHIP_ALREADY_TRANSFERRED`, `422 INVALID_TRANSFER` |

##### Tamagotchi Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateTamagotchiRequest` | `ownerUserId` | UUID string | Yes | Initial owner |
| `CreateTamagotchiRequest` | `packageId` | UUID string | Yes | Package that defines the Tamagotchi's local statistics |
| `CreateTamagotchiRequest` | `name` | String, 1-80 characters | Yes | Tamagotchi display name |
| `CreateTamagotchiRequest` | `combatType` | `FLAME`, `NATURE`, `EARTH`, `ELECTRIC`, `WATER`, or `SHADOW` | Yes | Predefined combat type |
| `CreateTamagotchiRequest` | `spriteUrl` | URL string | Yes | Sprite reference |
| `CreateTamagotchiRequest` | `healthStats` | JSON object | Yes | Package-local statistics validated against Package Registry definitions |
| `UpdateTamagotchiRequest` | `name` | String, 1-80 characters | No | Updated display name |
| `UpdateTamagotchiRequest` | `spriteUrl` | URL string | No | Updated sprite reference |
| `TamagotchiResponse` | `tamagotchiId` | UUID string | Yes | Global Tamagotchi identifier |
| `TamagotchiResponse` | `ownerUserId` | UUID string | Yes | Current owner |
| `TamagotchiResponse` | `packageId` | UUID string | Yes | Originating package |
| `TamagotchiResponse` | `name` | String | Yes | Display name |
| `TamagotchiResponse` | `ownershipRole` | `PRIMARY` or `SECONDARY` | Yes | Role for the current owner |
| `TamagotchiResponse` | `combatType` | Combat-type string | Yes | Current combat type |
| `TamagotchiResponse` | `level` | Positive integer | Yes | Current level |
| `TamagotchiResponse` | `xp` | Non-negative integer | Yes | Total accumulated XP |
| `TamagotchiResponse` | `spriteUrl` | URL string | Yes | Sprite reference |
| `TamagotchiResponse` | `healthStats` | JSON object | Yes | Non-normalized package-local statistics |
| `TamagotchiResponse` | `createdAt` | UTC timestamp | Yes | Creation time |
| `TamagotchiResponse` | `updatedAt` | UTC timestamp | Yes | Last update time |
| `SetPrimaryTamagotchiRequest` | `tamagotchiId` | UUID string | Yes | Owned Tamagotchi that becomes primary |
| `UpdateHealthStatsRequest` | `stats` | JSON object | Yes | Statistic keys and new values |

Package-local `healthStats` values may be integer, decimal, or Boolean values according to the definitions returned by Package Registry Service. Tamagotchi Service rejects unknown keys and values outside their configured ranges.

##### Combat and Progression Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CombatTypeResponse` | `type` | Combat-type string | Yes | One of the six predefined types |
| `CombatTypeResponse` | `strongAgainst` | Combat-type string | Yes | Type against which it has an advantage |
| `CombatProfileResponse` | `tamagotchiId` | UUID string | Yes | Tamagotchi identifier |
| `CombatProfileResponse` | `ownerUserId` | UUID string | Yes | Current owner |
| `CombatProfileResponse` | `packageId` | UUID string | Yes | Package used to interpret local statistics |
| `CombatProfileResponse` | `combatType` | Combat-type string | Yes | Type used for advantage calculations |
| `CombatProfileResponse` | `level` | Positive integer | Yes | Level used for combat calculations |
| `CombatProfileResponse` | `healthStats` | JSON object | Yes | Current package-local statistics |
| `GrantXpRequest` | `amount` | Positive integer | Yes | XP to grant |
| `GrantXpRequest` | `source` | `BATTLE` or `RAID` | Yes | Activity producing the XP |
| `GrantXpRequest` | `referenceId` | UUID string | Yes | Battle or raid identifier used for deduplication |
| `GrantXpResponse` | `tamagotchiId` | UUID string | Yes | Updated Tamagotchi |
| `GrantXpResponse` | `previousLevel` | Positive integer | Yes | Level before the grant |
| `GrantXpResponse` | `newLevel` | Positive integer | Yes | Level after the grant |
| `GrantXpResponse` | `totalXp` | Non-negative integer | Yes | Total XP after the grant |
| `GrantXpResponse` | `processedAt` | UTC timestamp | Yes | Grant processing time |

The type-advantage cycle is `FLAME > NATURE > EARTH > ELECTRIC > WATER > SHADOW > FLAME`.

##### Ownership Transfer Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `TransferTamagotchiRequest` | `tamagotchiId` | UUID string | Yes | Existing Tamagotchi to transfer |
| `TransferTamagotchiRequest` | `fromUserId` | UUID string | Yes | Current owner |
| `TransferTamagotchiRequest` | `toUserId` | UUID string | Yes | New owner |
| `TransferTamagotchiRequest` | `reason` | `BATTLE_REWARD` | Yes | Business reason for the transfer |
| `TransferTamagotchiRequest` | `referenceId` | UUID string | Yes | Completed battle identifier used for deduplication |
| `OwnershipTransferResponse` | `transferId` | UUID string | Yes | Ownership-transfer identifier |
| `OwnershipTransferResponse` | `tamagotchiId` | UUID string | Yes | Transferred Tamagotchi |
| `OwnershipTransferResponse` | `fromUserId` | UUID string | Yes | Previous owner |
| `OwnershipTransferResponse` | `toUserId` | UUID string | Yes | New owner |
| `OwnershipTransferResponse` | `newOwnershipRole` | `SECONDARY` | Yes | Role assigned to the captured Tamagotchi |
| `OwnershipTransferResponse` | `transferredAt` | UTC timestamp | Yes | Transfer completion time |

The transfer updates the existing Tamagotchi instead of creating a new entry. The winner receives it as a secondary Tamagotchi. Selection of a new primary for the previous owner is a separate user action.

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Outbound | Package Registry Service | Read package and statistic definitions | Validate package-local health statistics |
| Inbound | Battle Service | Read combat profile, grant XP, and transfer ownership | Execute and settle PvP combat |
| Inbound | Monster Raid Service | Read combat profile and grant XP | Calculate raid damage and distribute rewards |

#### Battle Service

Battle Service owns battle requests, active turn-based battles, actions, and final results. It reads authoritative user, Tamagotchi, and package configuration through service APIs and stores only battle-specific state in Redis.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `POST /api/v1/battle-requests` | Challenger | `CreateBattleRequest` | `201 BattleRequestResponse` | `400`, `403`, `404`, `409 BATTLE_REQUEST_EXISTS`, `422 INVALID_SELECTION` |
| `GET /api/v1/battle-requests/{battleRequestId}` | Challenger or opponent | None | `200 BattleRequestResponse` | `403`, `404 BATTLE_REQUEST_NOT_FOUND` |
| `GET /api/v1/users/{userId}/battle-requests?direction={direction}&status={status}` | Account owner | Query parameters | `200 BattleRequestResponse[]` | `400`, `403` |
| `POST /api/v1/battle-requests/{battleRequestId}/accept` | Opponent | `AcceptBattleRequest` | `201 BattleResponse` | `400`, `403`, `404`, `409 REQUEST_ALREADY_RESOLVED`, `422 INVALID_SELECTION` |
| `POST /api/v1/battle-requests/{battleRequestId}/reject` | Opponent | None | `200 BattleRequestResponse` | `403`, `404`, `409 REQUEST_ALREADY_RESOLVED` |
| `GET /api/v1/battles/{battleId}` | Participant | None | `200 BattleResponse` | `403`, `404 BATTLE_NOT_FOUND` |
| `GET /api/v1/users/{userId}/battles?status={status}&cursor={cursor}&limit={limit}` | Account owner | Query parameters | `200 BattlePageResponse` | `400`, `403` |
| `POST /api/v1/battles/{battleId}/actions` | Current-turn participant | `CreateBattleActionRequest` | `200 BattleActionResponse` | `400`, `403`, `404`, `409 NOT_CURRENT_TURN`, `422 INVALID_ACTION` |
| `POST /api/v1/battles/{battleId}/forfeit` | Participant | None | `200 BattleResponse` | `403`, `404`, `409 BATTLE_NOT_ACTIVE` |

##### Battle Request Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateBattleRequest` | `opponentUserId` | UUID string | Yes | User being challenged |
| `CreateBattleRequest` | `primaryTamagotchiId` | UUID string | Yes | Challenger's primary Tamagotchi |
| `CreateBattleRequest` | `secondaryTamagotchiId` | UUID string | Yes | Challenger's selected secondary Tamagotchi |
| `CreateBattleRequest` | `equippedBoosts` | Array of `BattleBoostSelection` | Yes | Package-defined boosts selected by the challenger |
| `AcceptBattleRequest` | `primaryTamagotchiId` | UUID string | Yes | Opponent's primary Tamagotchi |
| `AcceptBattleRequest` | `secondaryTamagotchiId` | UUID string | Yes | Opponent's selected secondary Tamagotchi |
| `AcceptBattleRequest` | `equippedBoosts` | Array of `BattleBoostSelection` | Yes | Package-defined boosts selected by the opponent |
| `BattleRequestResponse` | `battleRequestId` | UUID string | Yes | Challenge identifier |
| `BattleRequestResponse` | `challengerUserId` | UUID string | Yes | User who created the challenge |
| `BattleRequestResponse` | `opponentUserId` | UUID string | Yes | Challenged user |
| `BattleRequestResponse` | `challengerSelection` | `BattleSelection` | Yes | Challenger's Tamagotchis and boosts |
| `BattleRequestResponse` | `status` | `PENDING`, `ACCEPTED`, `REJECTED`, or `EXPIRED` | Yes | Current request state |
| `BattleRequestResponse` | `createdAt` | UTC timestamp | Yes | Challenge creation time |
| `BattleRequestResponse` | `expiresAt` | UTC timestamp | Yes | Time after which the challenge expires |
| `BattleSelection` | `primaryTamagotchiId` | UUID string | Yes | Selected primary Tamagotchi |
| `BattleSelection` | `secondaryTamagotchiId` | UUID string | Yes | Selected secondary Tamagotchi |
| `BattleSelection` | `equippedBoosts` | Array of `BattleBoostSelection` | Yes | Selected package-defined boosts |
| `BattleBoostSelection` | `packageId` | UUID string | Yes | Package defining the boost |
| `BattleBoostSelection` | `boostKey` | String | Yes | Boost key unique within the package |

##### Battle State and Action Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `BattleResponse` | `battleId` | UUID string | Yes | Battle identifier |
| `BattleResponse` | `battleRequestId` | UUID string | Yes | Request that created the battle |
| `BattleResponse` | `status` | `ACTIVE`, `SETTLING`, `COMPLETED`, or `FORFEITED` | Yes | Battle lifecycle state |
| `BattleResponse` | `participants` | Array of two `BattleParticipant` objects | Yes | Current state for both players |
| `BattleResponse` | `currentTurnUserId` | UUID string or `null` | Yes | User allowed to act, or `null` after the battle ends |
| `BattleResponse` | `turnNumber` | Positive integer | Yes | Current turn number |
| `BattleResponse` | `winnerUserId` | UUID string or `null` | Yes | Winner after completion |
| `BattleResponse` | `loserUserId` | UUID string or `null` | Yes | Loser after completion |
| `BattleResponse` | `result` | `BattleResult` or `null` | Yes | Settlement result after completion |
| `BattleResponse` | `createdAt` | UTC timestamp | Yes | Battle creation time |
| `BattleResponse` | `updatedAt` | UTC timestamp | Yes | Last state-change time |
| `BattlePageResponse` | `items` | Array of `BattleResponse` | Yes | Battles in the current page |
| `BattlePageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `BattleParticipant` | `userId` | UUID string | Yes | Participant identifier |
| `BattleParticipant` | `combatants` | Array of two `BattleCombatant` objects | Yes | Primary and secondary battle state |
| `BattleParticipant` | `equippedBoosts` | Array of `BattleBoostSelection` | Yes | Boosts available during the battle |
| `BattleCombatant` | `tamagotchiId` | UUID string | Yes | Participating Tamagotchi |
| `BattleCombatant` | `role` | `PRIMARY` or `SECONDARY` | Yes | Selection role |
| `BattleCombatant` | `currentHealth` | Non-negative integer | Yes | Current battle health |
| `BattleCombatant` | `defeated` | Boolean | Yes | Whether the Tamagotchi can continue fighting |
| `CreateBattleActionRequest` | `actionId` | UUID string | Yes | Client-generated identifier used for deduplication |
| `CreateBattleActionRequest` | `type` | `ATTACK`, `SWITCH_ACTIVE`, or `USE_BOOST` | Yes | Requested turn action |
| `CreateBattleActionRequest` | `actorTamagotchiId` | UUID string | Yes | Tamagotchi performing the action |
| `CreateBattleActionRequest` | `targetTamagotchiId` | UUID string | Conditional | Required for an attack |
| `CreateBattleActionRequest` | `boostPackageId` | UUID string | Conditional | Required when using a boost |
| `CreateBattleActionRequest` | `boostKey` | String | Conditional | Required when using a boost |
| `BattleActionResponse` | `actionId` | UUID string | Yes | Processed action identifier |
| `BattleActionResponse` | `type` | Battle-action string | Yes | Processed action type |
| `BattleActionResponse` | `damage` | Non-negative integer | Yes | Damage produced by the action; zero for non-damage actions |
| `BattleActionResponse` | `battle` | `BattleResponse` | Yes | Battle state after applying the action |

##### Battle Result Schema

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `BattleResult` | `winnerUserId` | UUID string | Yes | Winning player |
| `BattleResult` | `loserUserId` | UUID string | Yes | Losing player |
| `BattleResult` | `winnerGlobalCurrency` | Non-negative integer | Yes | Currency credited to the winner |
| `BattleResult` | `loserGlobalCurrencyLoss` | Non-negative integer | Yes | Currency debited from the loser |
| `BattleResult` | `xpAwards` | Array of `BattleXpAward` | Yes | XP distributed to all selected Tamagotchis |
| `BattleResult` | `transferredTamagotchiId` | UUID string | Yes | Loser's former primary Tamagotchi transferred to the winner |
| `BattleResult` | `settledAt` | UTC timestamp | Yes | Time at which all rewards and transfers completed |
| `BattleXpAward` | `userId` | UUID string | Yes | Owner at the time XP is awarded |
| `BattleXpAward` | `tamagotchiId` | UUID string | Yes | Tamagotchi receiving XP |
| `BattleXpAward` | `amount` | Non-negative integer | Yes | XP amount |

By default, each participant's total battle XP is split 60 percent to the primary Tamagotchi and 40 percent to the secondary Tamagotchi. The winner receives the larger total award and the loser receives a smaller total award.

##### Settlement Rules

When combat ends, Battle Service enters `SETTLING` and performs idempotent commands using `battleId` as the business reference:

1. Credit the winner and debit the loser through User Management Service.
2. Grant XP to both selected Tamagotchis through Tamagotchi Service.
3. Transfer the loser's primary Tamagotchi to the winner through Tamagotchi Service.
4. Mark the battle `COMPLETED` only after every required command succeeds.

If a dependency is unavailable, the battle remains `SETTLING` and the failed command can be retried without applying a reward twice. A completion event is published only after settlement succeeds.

##### Published Queue Events

`battle.request.created.v1` is published after a challenge is stored. Notification Service consumes it to notify the opponent.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `battleRequestId` | UUID string | Yes | Challenge identifier |
| `challengerUserId` | UUID string | Yes | User who created the challenge |
| `opponentUserId` | UUID string | Yes | User who should be notified |
| `expiresAt` | UTC timestamp | Yes | Challenge expiration time |

`battle.completed.v1` is published after currency, XP, and ownership settlement finishes. Notification Service consumes it to notify both players.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `battleId` | UUID string | Yes | Completed battle |
| `winnerUserId` | UUID string | Yes | Winning player |
| `loserUserId` | UUID string | Yes | Losing player |
| `winnerGlobalCurrency` | Non-negative integer | Yes | Winner's currency reward |
| `loserGlobalCurrencyLoss` | Non-negative integer | Yes | Loser's currency loss |
| `transferredTamagotchiId` | UUID string | Yes | Tamagotchi transferred to the winner |
| `settledAt` | UTC timestamp | Yes | Settlement completion time |

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Outbound | User Management Service | Read users and balances; create balance transactions | Validate participants and settle currency rewards and losses |
| Outbound | Tamagotchi Service | Read combat profiles; grant XP; transfer ownership | Calculate combat and settle progression and capture rewards |
| Outbound | Package Registry Service | Read statistic and battle-boost definitions | Calculate package-specific bonuses and validate equipped boosts |
| Outbound | Notification Service through Queue | Publish request and completion events | Notify challenged users and battle participants asynchronously |

#### Map Service

Map Service owns temporary location state and map visibility calculations. Clients continuously replace their latest location through the API Gateway. The service keeps only the newest update for each user in Redis and does not store location history.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `PUT /api/v1/users/{userId}/location` | Account owner | `UpdateLocationRequest` | `200 LocationResponse` | `400`, `403`, `404 USER_NOT_FOUND`, `409 STALE_LOCATION_UPDATE` |
| `GET /api/v1/users/{userId}/map` | Account owner | None | `200 MapViewResponse` | `403`, `404 USER_OR_LOCATION_NOT_FOUND`, `503 USER_SERVICE_UNAVAILABLE` |
| `DELETE /api/v1/users/{userId}/location` | Account owner | None | `204` | `403`, `404 LOCATION_NOT_FOUND` |

##### Location Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `UpdateLocationRequest` | `latitude` | Decimal from -90 to 90 | Yes | Latest latitude reported by the client |
| `UpdateLocationRequest` | `longitude` | Decimal from -180 to 180 | Yes | Latest longitude reported by the client |
| `UpdateLocationRequest` | `accuracyMeters` | Non-negative decimal | No | Accuracy reported by the device |
| `UpdateLocationRequest` | `recordedAt` | UTC timestamp | Yes | Time at which the device obtained the location |
| `UpdateLocationRequest` | `sequenceNumber` | Non-negative integer | Yes | Monotonically increasing client value used to reject out-of-order updates |
| `LocationResponse` | `userId` | UUID string | Yes | User associated with the location |
| `LocationResponse` | `latitude` | Decimal from -90 to 90 | Yes | Stored latitude |
| `LocationResponse` | `longitude` | Decimal from -180 to 180 | Yes | Stored longitude |
| `LocationResponse` | `accuracyMeters` | Non-negative decimal or `null` | Yes | Device accuracy when supplied |
| `LocationResponse` | `recordedAt` | UTC timestamp | Yes | Time at which the device obtained the location |
| `LocationResponse` | `expiresAt` | UTC timestamp | Yes | Time after which the location is no longer visible |

##### Map View Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `MapViewResponse` | `userId` | UUID string | Yes | User requesting the map |
| `MapViewResponse` | `generatedAt` | UTC timestamp | Yes | Time at which visibility was calculated |
| `MapViewResponse` | `players` | Array of `VisiblePlayer` | Yes | Users visible according to the relationship and proximity rules |
| `VisiblePlayer` | `userId` | UUID string | Yes | Visible user identifier |
| `VisiblePlayer` | `relationship` | `FRIEND`, `ENEMY`, or `NONE` | Yes | Relationship returned by User Management Service |
| `VisiblePlayer` | `latitude` | Decimal from -90 to 90 | Yes | Latest unexpired latitude |
| `VisiblePlayer` | `longitude` | Decimal from -180 to 180 | Yes | Latest unexpired longitude |
| `VisiblePlayer` | `distanceMeters` | Non-negative decimal | Yes | Calculated distance from the requesting user |
| `VisiblePlayer` | `recordedAt` | UTC timestamp | Yes | Time at which the visible location was obtained |

Friends and enemies are included whenever both users have unexpired locations. A user with relationship `NONE` is included only when the calculated distance is at most 6 meters. Expired locations are omitted from map results.

##### Published Queue Event

`map.proximity.detected.v1` is published when two unrelated users move from outside to inside the 6-meter threshold. Notification Service consumes it to notify the affected users.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `firstUserId` | UUID string | Yes | First nearby user |
| `secondUserId` | UUID string | Yes | Second nearby user |
| `distanceMeters` | Non-negative decimal | Yes | Distance calculated when the threshold was crossed |
| `detectedAt` | UTC timestamp | Yes | Detection time |

Map Service records a short-lived proximity marker for the unordered user pair so that continuous location updates do not produce duplicate notifications. A new event may be published only after the pair leaves the threshold and later enters it again.

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Outbound | User Management Service | Read users and friend/enemy relationships | Classify candidates and apply map visibility rules |
| Outbound | Notification Service through Queue | Publish proximity events | Request asynchronous nearby-player notifications without coupling Map Service to Firebase |

#### Monster Raid Service

Monster Raid Service owns each guild's active cooperative raid, its participants, attacks, timer, monster health, and settlement result. An active raid uses a snapshot of the selected Package Registry configuration so that later configuration changes cannot alter a raid already in progress. Active and recently finished raid state is stored in Redis.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /api/v1/raids?guildId={guildId}&status={status}&cursor={cursor}&limit={limit}` | Guild member | Query parameters | `200 RaidPageResponse` | `400`, `403`, `404 GUILD_NOT_FOUND` |
| `POST /api/v1/guilds/{guildId}/raids` | Guild member | `CreateRaidRequest` | `201 RaidResponse` | `400`, `403`, `404 SCHEDULE_OR_GUILD_NOT_FOUND`, `409 ACTIVE_GUILD_RAID_EXISTS`, `422 SCHEDULE_NOT_ACTIVE` |
| `GET /api/v1/raids/{raidId}` | Guild member | None | `200 RaidResponse` | `403`, `404 RAID_NOT_FOUND` |
| `POST /api/v1/raids/{raidId}/participants` | Guild member | `JoinRaidRequest` | `201 RaidParticipantResponse` | `400`, `403`, `404`, `409 PARTICIPANT_EXISTS`, `422 RAID_NOT_ACTIVE`, `422 PARTICIPANT_LIMIT_REACHED` |
| `GET /api/v1/raids/{raidId}/participants?cursor={cursor}&limit={limit}` | Guild member | Query parameters | `200 RaidParticipantPageResponse` | `400`, `403`, `404 RAID_NOT_FOUND` |
| `POST /api/v1/raids/{raidId}/attacks` | Raid participant | `CreateRaidAttackRequest` | `200 RaidAttackResponse` | `400`, `403`, `404`, `409 ATTACK_ALREADY_PROCESSED`, `422 RAID_NOT_ACTIVE` |
| `GET /api/v1/raids/{raidId}/result` | Guild member | None | `200 RaidResultResponse` | `403`, `404 RAID_NOT_FOUND`, `409 RAID_NOT_FINISHED` |

Creating a raid is idempotent for the combination of `guildId` and `scheduleId`: if concurrent requests attempt to create the same guild raid, only one active instance is stored.

##### Raid State Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `CreateRaidRequest` | `scheduleId` | UUID string | Yes | Active Package Registry schedule used to initialize the raid |
| `RaidResponse` | `raidId` | UUID string | Yes | Guild raid identifier |
| `RaidResponse` | `guildId` | UUID string | Yes | Guild participating in the raid |
| `RaidResponse` | `scheduleId` | UUID string | Yes | Schedule from which the raid was created |
| `RaidResponse` | `raidConfigurationId` | UUID string | Yes | Configuration snapshot source |
| `RaidResponse` | `status` | `ACTIVE`, `SETTLING`, `COMPLETED`, or `FAILED` | Yes | Current raid lifecycle state |
| `RaidResponse` | `monster` | `RaidMonsterState` | Yes | Current monster state |
| `RaidResponse` | `participantCount` | Non-negative integer | Yes | Number of joined participants |
| `RaidResponse` | `startsAt` | UTC timestamp | Yes | Raid activation time |
| `RaidResponse` | `endsAt` | UTC timestamp | Yes | Deadline copied from the active schedule |
| `RaidResponse` | `finishedAt` | UTC timestamp or `null` | Yes | Completion or failure time |
| `RaidPageResponse` | `items` | Array of `RaidResponse` | Yes | Raids in the current page |
| `RaidPageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `RaidMonsterState` | `name` | String | Yes | Monster name copied from the configuration |
| `RaidMonsterState` | `spriteUrl` | URL string | Yes | Monster sprite reference |
| `RaidMonsterState` | `maximumHp` | Positive integer | Yes | Monster health at raid start |
| `RaidMonsterState` | `currentHp` | Non-negative integer | Yes | Remaining monster health |
| `RaidMonsterState` | `weaknesses` | Array of combat-type strings | Yes | Types that deal increased damage |
| `RaidMonsterState` | `resistances` | Array of combat-type strings | Yes | Types that deal reduced damage |

##### Participant and Attack Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `JoinRaidRequest` | `primaryTamagotchiId` | UUID string | Yes | Participant's current primary Tamagotchi |
| `RaidParticipantResponse` | `raidId` | UUID string | Yes | Joined raid |
| `RaidParticipantResponse` | `userId` | UUID string | Yes | Participating guild member |
| `RaidParticipantResponse` | `tamagotchiId` | UUID string | Yes | Tamagotchi contributing damage |
| `RaidParticipantResponse` | `damageDealt` | Non-negative integer | Yes | Participant's accumulated damage |
| `RaidParticipantResponse` | `joinedAt` | UTC timestamp | Yes | Join time |
| `RaidParticipantPageResponse` | `items` | Array of `RaidParticipantResponse` | Yes | Participants in the current page |
| `RaidParticipantPageResponse` | `nextCursor` | String or `null` | Yes | Cursor for the next page |
| `CreateRaidAttackRequest` | `actionId` | UUID string | Yes | Client-generated identifier used for deduplication |
| `CreateRaidAttackRequest` | `tamagotchiId` | UUID string | Yes | Joined Tamagotchi performing the attack |
| `CreateRaidAttackRequest` | `performedAt` | UTC timestamp | Yes | Client-observed attack time used for validation |
| `RaidAttackResponse` | `actionId` | UUID string | Yes | Processed action identifier |
| `RaidAttackResponse` | `damage` | Non-negative integer | Yes | Damage applied by this attack |
| `RaidAttackResponse` | `monsterCurrentHp` | Non-negative integer | Yes | Remaining health after the attack |
| `RaidAttackResponse` | `raidStatus` | `ACTIVE` or `SETTLING` | Yes | State after applying the attack |
| `RaidAttackResponse` | `processedAt` | UTC timestamp | Yes | Server processing time |

Joining requires an active Guild Service membership and ownership of the submitted primary Tamagotchi. Damage is calculated from the Tamagotchi combat profile, the raid configuration snapshot, and the relevant package statistic definitions. The server rate-limits attacks and never trusts client-provided damage values.

##### Result and Reward Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `RaidResultResponse` | `raidId` | UUID string | Yes | Finished raid |
| `RaidResultResponse` | `status` | `COMPLETED` or `FAILED` | Yes | Whether the monster was defeated before the deadline |
| `RaidResultResponse` | `totalDamage` | Non-negative integer | Yes | Damage contributed by all participants |
| `RaidResultResponse` | `rewards` | Array of `RaidParticipantReward` | Yes | Per-participant rewards; empty for a failed raid |
| `RaidResultResponse` | `finishedAt` | UTC timestamp | Yes | Time at which the terminal state was reached |
| `RaidParticipantReward` | `userId` | UUID string | Yes | Rewarded participant |
| `RaidParticipantReward` | `tamagotchiId` | UUID string | Yes | Tamagotchi receiving XP |
| `RaidParticipantReward` | `globalCurrency` | Non-negative integer | Yes | Currency credited through User Management Service |
| `RaidParticipantReward` | `xp` | Non-negative integer | Yes | XP granted through Tamagotchi Service |

##### Completion and Failure Rules

When monster HP reaches zero, the raid enters `SETTLING` and performs idempotent reward commands using `raidId` as the business reference:

1. Credit each eligible participant through User Management Service.
2. Grant XP to each participating Tamagotchi through Tamagotchi Service.
3. Mark the raid `COMPLETED` only after all required reward commands succeed.

If a dependency is unavailable, the raid remains `SETTLING` and retries cannot apply a reward twice. If the deadline arrives while monster HP is above zero, the raid becomes `FAILED` and no rewards are distributed. Recently finished results remain available in Redis for a configured retention period; permanent raid history is outside the current architecture.

##### Published Queue Events

`raid.started.v1` is published after a guild raid is created. Notification Service consumes it to notify guild members.

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `raidId` | UUID string | Yes | Created guild raid |
| `guildId` | UUID string | Yes | Participating guild |
| `monsterName` | String | Yes | Name displayed in the notification |
| `recipientUserIds` | Array of UUID strings | Yes | Eligible guild members to notify |
| `startsAt` | UTC timestamp | Yes | Raid start time |
| `endsAt` | UTC timestamp | Yes | Raid deadline |

`raid.completed.v1` and `raid.failed.v1` share the following payload and are published only after the corresponding terminal state is stored:

| `data` field | Type | Required | Meaning |
|---|---|:---:|---|
| `raidId` | UUID string | Yes | Finished raid |
| `guildId` | UUID string | Yes | Participating guild |
| `status` | `COMPLETED` or `FAILED` | Yes | Final raid outcome |
| `participantUserIds` | Array of UUID strings | Yes | Users who participated |
| `finishedAt` | UTC timestamp | Yes | Time at which the terminal state was stored |

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Outbound | Guild Service | Read guild, members, and membership | Resolve notification recipients and validate raid visibility and participant eligibility |
| Outbound | Package Registry Service | Read active schedule, raid configuration, and statistic definitions | Initialize the raid and calculate package-specific damage |
| Outbound | Tamagotchi Service | Read combat profiles and grant XP | Validate combatants, calculate damage, and settle XP rewards |
| Outbound | User Management Service | Create balance transactions | Settle global-currency rewards |
| Outbound | Notification Service through Queue | Publish raid lifecycle events | Notify guild members and participants asynchronously |

#### Notification Service

Notification Service owns Firebase device registrations, user notification preferences, event deduplication, and delivery state. Business services never call Firebase directly; they publish domain events to the Queue, and Notification Service converts supported events into push messages.

##### Endpoint Catalog

| Method and path | Caller | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /api/v1/users/{userId}/notification-devices` | Account owner | None | `200 NotificationDeviceResponse[]` | `403` |
| `PUT /api/v1/users/{userId}/notification-devices/{deviceId}` | Account owner | `RegisterNotificationDeviceRequest` | `200 NotificationDeviceResponse` | `400`, `403`, `422 INVALID_FCM_TOKEN` |
| `DELETE /api/v1/users/{userId}/notification-devices/{deviceId}` | Account owner | None | `204` | `403`, `404 DEVICE_NOT_FOUND` |
| `GET /api/v1/users/{userId}/notification-preferences` | Account owner | None | `200 NotificationPreferencesResponse` | `403` |
| `PUT /api/v1/users/{userId}/notification-preferences` | Account owner | `UpdateNotificationPreferencesRequest` | `200 NotificationPreferencesResponse` | `400`, `403`, `422 UNKNOWN_CATEGORY` |

Device registration uses `PUT` because the same application installation may safely submit its current Firebase token multiple times. The authenticated JWT subject must equal `userId`; Notification Service does not accept a user identifier supplied only in the request body.

##### Device and Preference Schemas

| Schema | Field | Type | Required | Meaning |
|---|---|---|:---:|---|
| `RegisterNotificationDeviceRequest` | `fcmRegistrationToken` | String | Yes | Firebase token for the application installation |
| `RegisterNotificationDeviceRequest` | `platform` | `ANDROID`, `IOS`, or `WEB` | Yes | Device platform |
| `RegisterNotificationDeviceRequest` | `packageId` | UUID string | Yes | Tamagotchi application package registering the token |
| `RegisterNotificationDeviceRequest` | `appVersion` | String | No | Client version used for delivery diagnostics |
| `NotificationDeviceResponse` | `deviceId` | UUID string | Yes | Client-generated stable installation identifier |
| `NotificationDeviceResponse` | `userId` | UUID string | Yes | Owner of the registration |
| `NotificationDeviceResponse` | `packageId` | UUID string | Yes | Registered application package |
| `NotificationDeviceResponse` | `platform` | `ANDROID`, `IOS`, or `WEB` | Yes | Device platform |
| `NotificationDeviceResponse` | `enabled` | Boolean | Yes | Whether pushes may be sent to this registration |
| `NotificationDeviceResponse` | `registeredAt` | UTC timestamp | Yes | Initial registration time |
| `NotificationDeviceResponse` | `updatedAt` | UTC timestamp | Yes | Last token or metadata update |
| `UpdateNotificationPreferencesRequest` | `categories` | Object mapping category to Boolean | Yes | Complete enabled/disabled category selection |
| `NotificationPreferencesResponse` | `userId` | UUID string | Yes | Preference owner |
| `NotificationPreferencesResponse` | `categories` | Object mapping category to Boolean | Yes | Effective category settings |
| `NotificationPreferencesResponse` | `updatedAt` | UTC timestamp | Yes | Last preference update |

Supported categories are `FRIEND_REQUEST`, `PROXIMITY`, `BATTLE_REQUEST`, `BATTLE_RESULT`, `GUILD_INVITATION`, and `RAID_LIFECYCLE`. A missing preference record means that all categories are enabled by default. Firebase registration tokens are confidential: they are stored only by Notification Service, never returned in responses, and never written to logs.

##### Consumed Queue Events

All messages use the common asynchronous event envelope. The service extracts recipients only from the event payload and does not synchronously query a producer while processing an event.

| Event type | Producer | Recipient field | Notification category |
|---|---|---|---|
| `user.friend-request.created.v1` | User Management Service | `recipientUserId` | `FRIEND_REQUEST` |
| `map.proximity.detected.v1` | Map Service | `firstUserId` and `secondUserId` | `PROXIMITY` |
| `guild.invitation.created.v1` | Guild Service | `inviteeUserId` | `GUILD_INVITATION` |
| `battle.request.created.v1` | Battle Service | `opponentUserId` | `BATTLE_REQUEST` |
| `battle.completed.v1` | Battle Service | `winnerUserId` and `loserUserId` | `BATTLE_RESULT` |
| `raid.started.v1` | Monster Raid Service | `recipientUserIds` | `RAID_LIFECYCLE` |
| `raid.completed.v1` | Monster Raid Service | `participantUserIds` | `RAID_LIFECYCLE` |
| `raid.failed.v1` | Monster Raid Service | `participantUserIds` | `RAID_LIFECYCLE` |

Unknown event types or unsupported event versions are not converted into notifications. They are moved to a dead-letter flow for inspection instead of being silently acknowledged.

##### Firebase Delivery Contract

For each enabled recipient device, Notification Service sends an HTTPS request to Firebase Cloud Messaging containing:

| Field | Type | Required | Meaning |
|---|---|:---:|---|
| `token` | String | Yes | Confidential Firebase registration token |
| `notification.title` | String | Yes | Localizable short title |
| `notification.body` | String | Yes | Localizable human-readable message |
| `data.notificationId` | UUID string | Yes | Notification identifier used by the client |
| `data.category` | Notification-category string | Yes | Client routing category |
| `data.eventType` | Versioned event-type string | Yes | Domain event that produced the push |
| `data.resourceId` | UUID string | Yes | Primary resource to open, such as an invitation, battle, or raid |
| `data.correlationId` | UUID string | Yes | End-to-end tracing identifier |

All Firebase `data` values are encoded as strings. Provider-specific message identifiers and delivery attempts are stored internally but are not exposed to producing services.

##### Delivery and Retry Rules

Queue delivery is at least once. Before contacting Firebase, Notification Service creates a deduplication key from `eventId`, `recipientUserId`, and `deviceId`. Re-delivery of the same event therefore does not intentionally create another push for the same device.

- If the user's category is disabled or no enabled device exists, the event is recorded as skipped and acknowledged.
- A successful Firebase response is recorded and the queue message is acknowledged.
- Transient Firebase failures are retried with exponential backoff and a bounded attempt count.
- A permanently invalid Firebase token disables that device registration.
- A malformed event, unsupported version, or exhausted retry sequence is moved to a dead-letter flow with its `correlationId`.

Redis stores device registrations, preferences, deduplication keys, and recent delivery state. Deduplication and delivery records expire after a configured retention period; Notification Service is not a permanent notification-history service.

##### Service Dependencies

| Direction | Service | Operation | Reason |
|---|---|---|---|
| Inbound | User Management Service through Queue | Consume friend-request events | Deliver friend-request notifications |
| Inbound | Map Service through Queue | Consume proximity events | Deliver nearby-player notifications |
| Inbound | Guild Service through Queue | Consume invitation events | Deliver guild-invitation notifications |
| Inbound | Battle Service through Queue | Consume battle request and result events | Deliver battle notifications |
| Inbound | Monster Raid Service through Queue | Consume raid lifecycle events | Deliver raid notifications |
| Outbound | Firebase Cloud Messaging | Send push messages over the provider HTTPS API | Deliver notifications to registered client devices |

## Project Management

Tasks are tracked on the [GitHub Project board](https://github.com/users/m33ga/projects/1). Work is defined through issues (use the issue templates) and assigned before development starts.

## Development Guidelines

### Getting Started

Every teammate must install the pre-commit hooks after cloning:

```bash
pip install pre-commit
pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg
```

### Workflow

We use **trunk-based development**: `main` is the single long-lived branch, and all work happens in short-lived branches merged back via pull requests.

1. Pick or create an issue and assign yourself.
2. Branch off `main` following the naming convention.
3. Commit using Conventional Commits.
4. Open a PR (the template will guide you), get at least **1 approval**, pass the CI checks.
5. **Squash and merge**.

### Branch Naming

Branches must match `<type>/<short-description>` (lowercase letters, digits, `.`, `_`, `-`), enforced by CI:

| Type | Used for | Example |
|------|----------|---------|
| `feat` | New functionality | `feat/battle-service` |
| `fix` | Bug fixes | `fix/currency-overflow` |
| `docs` | Documentation only | `docs/communication-contract` |
| `chore` | Maintenance, tooling | `chore/pre-commit-setup` |
| `refactor` | Code restructuring, no behavior change | `refactor/user-repo` |
| `test` | Adding or fixing tests | `test/battle-damage` |
| `ci` | CI/CD changes | `ci/branch-name-check` |
| `perf` / `build` / `revert` | Performance, build system, reverts | `perf/map-queries` |
| `release` | Lab release branches | `release/lab-1` |
| `hotfix` | Urgent fixes on releases | `hotfix/login-crash` |

### Commits

All commit messages and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]
```

### Versioning and Releases

Versioning based on labs: `v{lab}.{iteration}.{patch}`

| Version | Meaning | Example |
|---------|---------|---------|
| `vX.0.0` | Lab X completed | `v1.0.0`, `v2.0.0` |
| `vX.Y.0` | Feature iteration within lab X | `v2.1.0`, `v2.2.0` |
| `vX.0.Z` | Bug fix / patch | `v2.0.1`, `v2.0.2` |

Lab release process:

1. Create `release/lab-X` from `main` when the lab requirements are complete.
2. Final testing and submission preparation on the release branch.
3. Tag the completion: `git tag vX.0.0`.
4. Submit and apply fixes during evaluation on the release branch.
5. Merge back to `main` when accepted.

### CI and Security Checks

| Check | What it does | When |
|-------|--------------|------|
| Conventional Commits | Validates the PR title and every commit message | On every PR |
| Branch Name | Validates the branch naming convention | On every PR |
| GitGuardian | Server-side secret scanning | On every push / PR |
| pre-commit + gitleaks | Local secret scanning, whitespace/YAML hygiene, commit message format | Before every local commit |

**Never** commit `.env` files, API keys or credentials.
