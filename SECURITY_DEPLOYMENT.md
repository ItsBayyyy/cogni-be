# Security deployment checklist

Source-code hardening is only effective after these deployment steps are
completed. Never commit generated values.

## 1. Rotate credentials

Generate independent values:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store them in the backend deployment secret manager as:

- `JWT_SECRET`
- `OTP_PEPPER`
- `FALLBACK_ENCRYPTION_KEY`

Revoke the old JWT secret and invalidate existing sessions. Rotate any demo
account password that appeared in repository history.

## 2. Configure production services

Backend:

- Set `CORS_ORIGINS` to the exact HTTPS frontend origin.
- Set `REDIS_URL` to the production Redis endpoint so rate limits are shared
  across all application instances.
- Set `TRUSTED_PROXY_IPS` only to proxy networks that overwrite forwarded
  client-IP headers. Leave it empty if that guarantee is unavailable.

Frontend:

- Set `COGNIFLIP_API_BASE_URL` to the backend `/api/v1` URL. This variable is
  server-only and must not use a `NEXT_PUBLIC_` prefix.
- Set `SITE_URL` to the exact HTTPS frontend origin.

## 3. Apply the database migration

Back up the database, then apply:

```text
migrations/001_security_hardening.sql
```

The migration intentionally invalidates outstanding OTP records, replaces
plaintext OTP storage with keyed digests, and adds token-version revocation.
Deploy the migrated backend immediately after applying it.

## 4. Purge exposed Git history

Coordinate this step with every contributor because it rewrites commit IDs:

1. Make a protected backup of the repositories.
2. Use `git filter-repo` to remove committed `.env` files and known credential
   literals from all refs.
3. Review the rewritten history with a secret scanner.
4. Force-push all rewritten branches and tags.
5. Require every contributor to re-clone instead of merging old history.

History rewriting does not replace credential rotation; rotate first.

## 5. Release verification

Before opening production traffic:

- Verify login, OTP verification, password reset, logout, and token expiry.
- Verify a user cannot read or mutate another user's session by changing IDs.
- Verify cross-origin state-changing requests receive `403`.
- Verify repeated login/OTP/reset attempts receive `429` across separate app
  instances.
- Verify browser storage and API responses never contain an access token.
- Verify application logs contain no email addresses, tokens, OTPs, transcript
  text, or provider response bodies.
