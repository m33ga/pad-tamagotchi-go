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
