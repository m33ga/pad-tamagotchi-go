DROP INDEX battle.ux_battles_active_first_user;
DROP INDEX battle.ux_battles_active_second_user;

CREATE TABLE battle.battle_participants (
    battle_id uuid NOT NULL REFERENCES battle.battles(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    position smallint NOT NULL,
    status varchar(16) NOT NULL,
    PRIMARY KEY (battle_id, user_id),
    CONSTRAINT uq_battle_participants_position UNIQUE (battle_id, position),
    CONSTRAINT ck_battle_participants_position CHECK (position IN (0, 1)),
    CONSTRAINT ck_battle_participants_status CHECK (
        status IN ('ACTIVE', 'SETTLING', 'COMPLETED', 'FORFEITED')
    )
);

CREATE UNIQUE INDEX ux_battle_participants_active_user
    ON battle.battle_participants (user_id)
    WHERE status IN ('ACTIVE', 'SETTLING');
