CREATE TABLE IF NOT EXISTS user_management.idempotency_records (
    "Scope" character varying(160) NOT NULL,
    "Key" uuid NOT NULL,
    "RequestFingerprint" text NOT NULL,
    "ResponseJson" jsonb NOT NULL,
    "CreatedAt" timestamp with time zone NOT NULL,
    CONSTRAINT "PK_idempotency_records" PRIMARY KEY ("Scope", "Key")
);

ALTER TABLE user_management.ledger_entries
    DROP CONSTRAINT IF EXISTS ck_ledger_amount;
ALTER TABLE user_management.ledger_entries
    ADD CONSTRAINT ck_ledger_amount CHECK ("Amount" <> 0);

ALTER TABLE user_management.ledger_entries
    DROP CONSTRAINT IF EXISTS ck_ledger_balance;
ALTER TABLE user_management.ledger_entries
    ADD CONSTRAINT ck_ledger_balance CHECK ("ResultingBalance" >= 0);

ALTER TABLE user_management.ledger_entries
    DROP CONSTRAINT IF EXISTS ck_ledger_currency;
ALTER TABLE user_management.ledger_entries
    ADD CONSTRAINT ck_ledger_currency CHECK (
        ("Currency" = 'GLOBAL' AND "PackageId" IS NULL)
        OR ("Currency" = 'LOCAL' AND "PackageId" IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS "IX_idempotency_records_CreatedAt"
    ON user_management.idempotency_records ("CreatedAt");

CREATE UNIQUE INDEX IF NOT EXISTS "UX_friend_requests_pending_pair"
    ON user_management.friend_requests (
        LEAST("SenderUserId", "RecipientUserId"),
        GREATEST("SenderUserId", "RecipientUserId")
    )
    WHERE "Status" = 'PENDING';
