BEGIN;

-- Normalize any legacy value before enforcing the server-owned allowlist.
UPDATE sessions
SET persona = 'friendly'
WHERE persona NOT IN ('friendly', 'strict', 'socratic', 'comedian', 'nain');

ALTER TABLE sessions
    DROP CONSTRAINT IF EXISTS sessions_persona_check,
    ADD CONSTRAINT sessions_persona_check
        CHECK (persona IN ('friendly', 'strict', 'socratic', 'comedian', 'nain'));

COMMIT;
