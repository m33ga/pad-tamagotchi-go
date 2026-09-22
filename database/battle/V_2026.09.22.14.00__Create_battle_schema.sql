CREATE SCHEMA IF NOT EXISTS battle;

CREATE TABLE battle.battle_requests (
    id uuid PRIMARY KEY,
    challenger_user_id uuid NOT NULL,
    opponent_user_id uuid NOT NULL,
    challenger_selection jsonb NOT NULL,
    status varchar(16) NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    decision_fingerprint text,
    decision_response jsonb,
    CONSTRAINT ck_battle_requests_distinct_users CHECK (challenger_user_id <> opponent_user_id),
    CONSTRAINT ck_battle_requests_status CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED'))
);

CREATE INDEX ix_battle_requests_challenger_user_id
    ON battle.battle_requests (challenger_user_id);
CREATE INDEX ix_battle_requests_opponent_user_id
    ON battle.battle_requests (opponent_user_id);
CREATE INDEX ix_battle_requests_status_expires_at
    ON battle.battle_requests (status, expires_at);
CREATE UNIQUE INDEX ux_battle_requests_pending_pair
    ON battle.battle_requests (
        LEAST(challenger_user_id, opponent_user_id),
        GREATEST(challenger_user_id, opponent_user_id)
    ) WHERE status = 'PENDING';

CREATE TABLE battle.battles (
    id uuid PRIMARY KEY,
    battle_request_id uuid NOT NULL UNIQUE REFERENCES battle.battle_requests(id),
    first_user_id uuid NOT NULL,
    second_user_id uuid NOT NULL,
    status varchar(16) NOT NULL,
    state jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_battles_distinct_users CHECK (first_user_id <> second_user_id),
    CONSTRAINT ck_battles_status CHECK (status IN ('ACTIVE', 'SETTLING', 'COMPLETED', 'FORFEITED'))
);

CREATE INDEX ix_battles_first_user_id_status_created_at
    ON battle.battles (first_user_id, status, created_at);
CREATE INDEX ix_battles_second_user_id_status_created_at
    ON battle.battles (second_user_id, status, created_at);
CREATE UNIQUE INDEX ux_battles_active_first_user
    ON battle.battles (first_user_id) WHERE status IN ('ACTIVE', 'SETTLING');
CREATE UNIQUE INDEX ux_battles_active_second_user
    ON battle.battles (second_user_id) WHERE status IN ('ACTIVE', 'SETTLING');

CREATE TABLE battle.battle_actions (
    battle_id uuid NOT NULL REFERENCES battle.battles(id) ON DELETE CASCADE,
    action_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    fingerprint text NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (battle_id, action_id)
);

CREATE TABLE battle.idempotency_records (
    scope text NOT NULL,
    actor_user_id uuid NOT NULL,
    command_key uuid NOT NULL,
    fingerprint text NOT NULL,
    response jsonb NOT NULL,
    status_code integer NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (scope, actor_user_id, command_key)
);

CREATE TABLE battle.battle_cursors (
    token text PRIMARY KEY,
    user_id uuid NOT NULL,
    status varchar(16),
    remaining_ids uuid[] NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_battle_cursors_status CHECK (
        status IS NULL OR status IN ('ACTIVE', 'SETTLING', 'COMPLETED', 'FORFEITED')
    )
);

CREATE TABLE battle.settlement_steps (
    battle_id uuid NOT NULL REFERENCES battle.battles(id) ON DELETE CASCADE,
    step text NOT NULL,
    completed_at timestamptz NOT NULL,
    PRIMARY KEY (battle_id, step)
);

CREATE TABLE battle.outbox_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    version integer NOT NULL,
    occurred_at timestamptz NOT NULL,
    source text NOT NULL,
    correlation_id uuid NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0,
    CONSTRAINT ck_outbox_events_version CHECK (version > 0),
    CONSTRAINT ck_outbox_events_publish_attempts CHECK (publish_attempts >= 0)
);

CREATE INDEX ix_outbox_events_published_at ON battle.outbox_events (published_at);
