# Tamagotchi Go

Virtual pets and beating up your friends. A distributed system.

Players raise Tamagotchis in apps of their own creation, all connected to a common backend where these worlds meet: encounter nearby players, battle their creatures, join guilds and take down raid monsters together, while keeping your own pet from starving to death.

Developed for the PAD (Distributed Applications Programming) course at FAF, Technical University of Moldova.

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
