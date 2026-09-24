CREATE TABLE IF NOT EXISTS guilds (
    guild_id UUID PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE,
    description VARCHAR(1000) NOT NULL,
    owner_id UUID NOT NULL,
    required_package_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guild_members (
    guild_id UUID NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('OWNER', 'OFFICER', 'MEMBER')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS guild_invitations (
    invitation_id UUID PRIMARY KEY,
    guild_id UUID NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    inviter_user_id UUID NOT NULL,
    invitee_user_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS guild_invitations_one_pending
    ON guild_invitations (guild_id, invitee_user_id)
    WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS guild_messages (
    message_id UUID PRIMARY KEY,
    guild_id UUID NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    author_user_id UUID NOT NULL,
    client_message_id UUID NOT NULL,
    content VARCHAR(2000) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, client_message_id)
);

CREATE TABLE IF NOT EXISTS outbox_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    event_version INTEGER NOT NULL,
    producer VARCHAR(80) NOT NULL,
    correlation_id UUID NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS guild_members_user_idx ON guild_members (user_id);
CREATE INDEX IF NOT EXISTS guild_invitations_invitee_idx ON guild_invitations (invitee_user_id, status);
CREATE INDEX IF NOT EXISTS guild_messages_guild_sent_idx ON guild_messages (guild_id, sent_at DESC);
