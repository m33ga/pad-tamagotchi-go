CREATE TABLE IF NOT EXISTS packages (
    package_id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    version VARCHAR(64) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS package_developers (
    package_id UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    PRIMARY KEY (package_id, user_id)
);

CREATE TABLE IF NOT EXISTS package_moderators (
    package_id UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (package_id, user_id)
);

CREATE TABLE IF NOT EXISTS package_registrations (
    package_id UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL UNIQUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (package_id, user_id)
);

CREATE TABLE IF NOT EXISTS stat_definitions (
    package_id UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
    definition_key VARCHAR(120) NOT NULL,
    definition JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (package_id, definition_key)
);

CREATE TABLE IF NOT EXISTS battle_boosts (
    package_id UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
    boost_key VARCHAR(120) NOT NULL,
    definition JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (package_id, boost_key)
);

CREATE TABLE IF NOT EXISTS raid_configurations (
    raid_configuration_id UUID PRIMARY KEY,
    configuration JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raid_schedules (
    schedule_id UUID PRIMARY KEY,
    raid_configuration_id UUID NOT NULL REFERENCES raid_configurations(raid_configuration_id),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('SCHEDULED', 'ACTIVE', 'INACTIVE', 'CANCELLED', 'COMPLETED')),
    created_by_admin_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS package_registrations_user_idx ON package_registrations (user_id);
CREATE INDEX IF NOT EXISTS raid_schedules_time_idx ON raid_schedules (starts_at, ends_at);
