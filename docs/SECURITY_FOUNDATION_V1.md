# Security Foundation V1

The commercial security layer creates no default administrator and stores no raw password, session, CSRF or enrollment token. Every user belongs to an organization and every authorization decision requires both organization scope and role.

## Controls

- explicit strong first-run password only;
- scrypt password hashing with per-user random salt;
- durable server-side sessions with hashed tokens, expiry and revocation;
- hashed CSRF tokens for state-changing requests;
- optional client fingerprint binding;
- organization-scoped RBAC (`admin`, `operator`, `viewer`);
- expiring, usage-limited, organization-scoped enrollment tokens;
- durable fixed-window rate limiting;
- tamper-evident chained audit events;
- external secret references instead of plaintext software credentials.

## Integration rules

- login must rate-limit by organization, username and source address;
- session cookies must be Secure, HttpOnly and SameSite;
- state-changing routes must validate both session and CSRF;
- every query must include the authenticated organization ID;
- administrative changes must append an audit event;
- plaintext `password_value`, `mfa_recovery` and similar fields must not enter commercial exports or APIs;
- TLS termination is mandatory for non-local deployments.

## Production promotion gate

Security modules must be integrated into the new modular commercial API, then pass API-level authentication, authorization, CSRF, rate-limit, session revocation, organization-isolation and audit-tamper tests before any customer pilot.
