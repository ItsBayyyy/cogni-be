BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE otps
    ADD COLUMN IF NOT EXISTS otp_digest CHAR(64),
    ADD COLUMN IF NOT EXISTS purpose VARCHAR(16),
    ADD COLUMN IF NOT EXISTS attempts SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMP WITH TIME ZONE;

-- Existing OTPs cannot be migrated safely from plaintext. Invalidate them.
DELETE FROM otps;

ALTER TABLE otps
    DROP COLUMN IF EXISTS otp_code,
    ALTER COLUMN otp_digest SET NOT NULL,
    ALTER COLUMN purpose SET NOT NULL,
    ADD CONSTRAINT otps_purpose_check CHECK (purpose IN ('verify', 'reset')),
    ADD CONSTRAINT otps_attempts_check CHECK (attempts >= 0 AND attempts <= 5);

DROP INDEX IF EXISTS idx_otps_email;
CREATE INDEX IF NOT EXISTS idx_otps_email_purpose_created
    ON otps(email, purpose, created_at DESC);

COMMIT;
