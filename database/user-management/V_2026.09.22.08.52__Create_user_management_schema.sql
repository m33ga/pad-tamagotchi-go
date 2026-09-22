CREATE SCHEMA IF NOT EXISTS user_management;

CREATE TABLE IF NOT EXISTS user_management.users (
    "Id" uuid NOT NULL,
    "Username" character varying(32) NOT NULL,
    "NormalizedUsername" character varying(32) NOT NULL,
    "Email" character varying(254) NOT NULL,
    "NormalizedEmail" character varying(254) NOT NULL,
    "PasswordHash" character varying(1024) NOT NULL,
    "InitialPackageId" uuid NOT NULL,
    "CreatedAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_users" PRIMARY KEY ("Id")
);

CREATE TABLE IF NOT EXISTS user_management.friend_requests (
    "Id" uuid NOT NULL,
    "SenderUserId" uuid NOT NULL,
    "RecipientUserId" uuid NOT NULL,
    "Status" character varying(16) NOT NULL,
    "CreatedAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_friend_requests" PRIMARY KEY ("Id"),
    CONSTRAINT ck_friend_request_status CHECK ("Status" IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT ck_friend_request_users CHECK ("SenderUserId" <> "RecipientUserId"),
    CONSTRAINT "FK_friend_requests_users_RecipientUserId" FOREIGN KEY ("RecipientUserId")
        REFERENCES user_management.users ("Id") ON DELETE RESTRICT,
    CONSTRAINT "FK_friend_requests_users_SenderUserId" FOREIGN KEY ("SenderUserId")
        REFERENCES user_management.users ("Id") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS user_management.ledger_entries (
    "Id" uuid NOT NULL,
    "UserId" uuid NOT NULL,
    "Currency" character varying(16) NOT NULL,
    "PackageId" uuid,
    "Reason" character varying(64) NOT NULL,
    "ReferenceId" uuid NOT NULL,
    "Amount" bigint NOT NULL,
    "ResultingBalance" bigint NOT NULL,
    "RequestFingerprint" text NOT NULL,
    "CreatedAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_ledger_entries" PRIMARY KEY ("Id"),
    CONSTRAINT "FK_ledger_entries_users_UserId" FOREIGN KEY ("UserId")
        REFERENCES user_management.users ("Id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_management.relationships (
    "SourceUserId" uuid NOT NULL,
    "TargetUserId" uuid NOT NULL,
    "Kind" character varying(16) NOT NULL,
    "CreatedAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_relationships" PRIMARY KEY ("SourceUserId", "TargetUserId"),
    CONSTRAINT ck_relationship_kind CHECK ("Kind" IN ('FRIEND', 'ENEMY')),
    CONSTRAINT ck_relationship_users CHECK ("SourceUserId" <> "TargetUserId"),
    CONSTRAINT "FK_relationships_users_SourceUserId" FOREIGN KEY ("SourceUserId")
        REFERENCES user_management.users ("Id") ON DELETE RESTRICT,
    CONSTRAINT "FK_relationships_users_TargetUserId" FOREIGN KEY ("TargetUserId")
        REFERENCES user_management.users ("Id") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS user_management.sessions (
    "Id" uuid NOT NULL,
    "UserId" uuid NOT NULL,
    "RefreshHash" character varying(64) NOT NULL,
    "ExpiresAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_sessions" PRIMARY KEY ("Id"),
    CONSTRAINT "FK_sessions_users_UserId" FOREIGN KEY ("UserId")
        REFERENCES user_management.users ("Id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_management.user_packages (
    "UserId" uuid NOT NULL,
    "PackageId" uuid NOT NULL,
    "RegisteredAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_user_packages" PRIMARY KEY ("UserId", "PackageId"),
    CONSTRAINT "FK_user_packages_users_UserId" FOREIGN KEY ("UserId")
        REFERENCES user_management.users ("Id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_management.wallets (
    "Id" uuid NOT NULL,
    "UserId" uuid NOT NULL,
    "Currency" character varying(16) NOT NULL,
    "PackageId" uuid,
    "Balance" bigint NOT NULL,
    CONSTRAINT "PK_wallets" PRIMARY KEY ("Id"),
    CONSTRAINT ck_wallet_balance CHECK ("Balance" >= 0),
    CONSTRAINT ck_wallet_currency CHECK (
        ("Currency" = 'GLOBAL' AND "PackageId" IS NULL)
        OR ("Currency" = 'LOCAL' AND "PackageId" IS NOT NULL)
    ),
    CONSTRAINT "FK_wallets_users_UserId" FOREIGN KEY ("UserId")
        REFERENCES user_management.users ("Id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "IX_friend_requests_RecipientUserId"
    ON user_management.friend_requests ("RecipientUserId");
CREATE INDEX IF NOT EXISTS "IX_friend_requests_SenderUserId_RecipientUserId_Status"
    ON user_management.friend_requests ("SenderUserId", "RecipientUserId", "Status");
CREATE UNIQUE INDEX IF NOT EXISTS "IX_ledger_entries_UserId_Currency_PackageId_Reason_ReferenceId"
    ON user_management.ledger_entries ("UserId", "Currency", "PackageId", "Reason", "ReferenceId")
    NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS "IX_relationships_TargetUserId"
    ON user_management.relationships ("TargetUserId");
CREATE INDEX IF NOT EXISTS "IX_sessions_ExpiresAt"
    ON user_management.sessions ("ExpiresAt");
CREATE UNIQUE INDEX IF NOT EXISTS "IX_sessions_RefreshHash"
    ON user_management.sessions ("RefreshHash");
CREATE INDEX IF NOT EXISTS "IX_sessions_UserId"
    ON user_management.sessions ("UserId");
CREATE UNIQUE INDEX IF NOT EXISTS "IX_users_NormalizedEmail"
    ON user_management.users ("NormalizedEmail");
CREATE UNIQUE INDEX IF NOT EXISTS "IX_users_NormalizedUsername"
    ON user_management.users ("NormalizedUsername");
CREATE UNIQUE INDEX IF NOT EXISTS "IX_wallets_UserId_Currency_PackageId"
    ON user_management.wallets ("UserId", "Currency", "PackageId") NULLS NOT DISTINCT;
