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

This service consults the **Tamagotchi Service** for combat stats, the **User Management Service** to credit/debit currency and XP and to transfer ownership of the loser's Tamagotchi, and the **Package Registry Service** for package-specific combat bonuses.

### Map Service

Receives continuous geolocation updates from the user's application. It stores the user's latest known coordinates and timestamp, discarding or ignoring stale locations.

It provides a map of nearby users: friends and enemies are always visible, while unknown users become relevant only when they come within roughly **6 meters** of one another. When two previously unrelated users cross the proximity threshold, the service generates an event that can result in suggestions to befriend or battle one another.

The service **does not** directly manage battles or notifications — it only emits proximity events. It relies on the **User Management Service** for friend/enemy relationships and publishes events consumed by the **Notification Service**.

### Guild Service

Allows users to create and participate in guilds, maintaining guild identity, membership, roles, and permissions. A guild may have an owner/leader, officers, and ordinary members.

It provides **Guild Chat**, letting members communicate in real time. Messages are associated with a guild and carry timestamps and authors; the service may use **WebSockets** directly for the guild-chat connection.

Guilds act as the social context for **Monster Raids**: members can join an active raid and their primary Tamagotchis become participants in the shared battle. Membership and invitation rules use the **Package Registry Service** (Registry) to determine the identity and relationship of users.

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

It consumes events published by other services (notably the **Map Service**, **Battle Service**, **Guild Service**, and **Monster Raid Service**) and delivers them to the appropriate clients.

## Architecture Diagram

Requests flow from the client through a load balancer to the API Gateway, which fronts the microservices. Each service owns its own database. Synchronous calls (solid arrows) handle request/response between services, while asynchronous events (dotted arrows) are published to the Notification Service, which delivers push notifications via Firebase Cloud Messaging.

![Architecture Diagram](docs/architecture.png)

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


## Service Ownership and Technology Stack

| Service | Owner | Language | Framework | Database |
|---|---|---|---|---|
| User Management Service | Sanda | C# | ASP.NET Core 10 + EF Core | PostgreSQL |
| Tamagotchi Service | Ion | Go | Go | MongoDB |
| Battle Service | Sanda | C# | ASP.NET Core 10 + EF Core | Redis |
| Map Service | Mihai | Go | Go | Redis |
| Guild Service | Cosmin | Go | Go | PostgreSQL |
| Monster Raid Service | Mihai | Go | Go | Redis |
| Package Registry Service | Cosmin | Go | Go | MongoDB |
| Notification Service | Ion | Go | Go | Redis |

### User Management Service — Sanda

The User Management Service is responsible for global user identity and account information. It handles authentication, user relationships such as friends and enemies, and global currency.

The service uses **C# with ASP.NET Core 10**. Entity Framework Core is used for data access because the service works with structured relational data.

**PostgreSQL** is used as the database because users, accounts, relationships and currency require structured data, relationships and transactional consistency.

### Battle Service — Sanda

The Battle Service is responsible for executing turn-based PvP battles between players. It calculates combat damage, manages battle state and processes battle rewards.

The service uses **C# with ASP.NET Core 10**. Entity Framework Core is available for structured persistent data access.

**Redis** is used for battle state because battles require fast access to frequently changing, temporary state such as the current turn, health and battle status.

### Tamagotchi Service — Ion

The Tamagotchi Service maintains the globally relevant state of Tamagotchis, including ownership, level, combat type and package-specific health statistics.

The service uses **Go** because the service is lightweight and benefits from Go's efficient concurrency model.

**MongoDB** is used because Tamagotchi statistics are package-specific and can have different structures between packages. A document-oriented database provides the required flexibility.

### Notification Service — Ion

The Notification Service handles asynchronous notifications sent to users through Firebase Cloud Messaging. It consumes events generated by other services and delivers notifications to clients.

The service uses **Go** because it is well suited for lightweight concurrent event processing.

**Redis** is used for fast-access notification and event-related data where low latency is important.

### Map Service — Mihai

The Map Service receives users' latest geographical positions and determines which users are nearby. It also generates proximity events.

The service uses **Go** because it continuously processes location updates and benefits from efficient concurrent processing.

**Redis** is used because the latest user locations are frequently updated and require very fast reads and writes.

### Guild Service — Cosmin

The Guild Service manages guilds, memberships, roles, permissions and guild chat. It also provides the social context required by Monster Raids.

The service uses **Go** because it handles concurrent interactions and real-time guild communication.

**PostgreSQL** is used because guild membership, roles and permissions are structured relational data with clear relationships and consistency requirements.

### Monster Raid Service — Mihai

The Monster Raid Service manages cooperative raids, including monster health, participants, damage, raid duration and rewards.

The service uses **Go** because raid interactions require efficient concurrent processing of multiple players participating in the same raid.

**Redis** is used for the frequently changing raid state, such as monster HP, participants and active raid status.

### Package Registry Service — Cosmin

The Package Registry Service manages application packages and package-specific game configuration. It stores package information, developers, moderators and package-specific Tamagotchi statistics.

The service uses **Go** for a lightweight distributed configuration service.

**MongoDB** is used because different packages can define different, non-normalized Tamagotchi statistics and configuration structures. MongoDB allows these documents to evolve without requiring a fixed relational schema.

## Technology Stack Rationale

### C#

C# is used for services that benefit from the mature ASP.NET Core ecosystem and strongly typed application development. ASP.NET Core 10 provides the framework for implementing HTTP APIs and backend business logic, while Entity Framework Core simplifies access to relational databases.

### Go

Go is used for lightweight distributed services that require efficient concurrency and low runtime overhead. Its goroutines and simple concurrency model make it suitable for services such as Map, Notification, Monster Raid and other event-driven or highly concurrent components.

### PostgreSQL

PostgreSQL is used when data has a strong relational structure and requires transactional consistency. It is therefore appropriate for User Management and Guild Service.

### MongoDB

MongoDB is used for flexible document-oriented data. It is particularly useful for Tamagotchi and Package Registry because different packages can define different statistics and configurations.

### Redis

Redis is used for high-speed, frequently changing or temporary state. It is appropriate for Battle, Map, Monster Raid and Notification workloads where low-latency access is important.

### Database-per-Service

Each microservice owns its database instead of directly sharing another service's database. This reduces coupling between services and allows each service to choose the database technology that best fits its data and workload.