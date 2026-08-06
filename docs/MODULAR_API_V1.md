# Modular Commercial API V1

The commercial API is separated from the live monolithic `server.py`. It is framework-independent and exposes a PEP 3333 adapter so the same tested application contracts can run behind a production HTTPS reverse proxy and supported application server.

## Implemented routes

- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/users`
- `GET /api/v1/users?limit=&offset=&q=`
- `POST /api/v1/enrollment-tokens`
- `POST /api/v1/messages`
- `GET /api/v1/messages?limit=&offset=`
- `GET /api/v1/messages/{message_id}`

## Security and performance contracts

- login is rate-limited by organization, username and source address;
- sessions, CSRF, roles and organization scope are enforced before service calls;
- state-changing user and message routes require CSRF;
- request bodies are bounded and require JSON;
- errors have stable codes and do not expose tracebacks;
- responses include request IDs and restrictive security/cache headers;
- listing routes use bounded server-side pagination;
- database connections are opened per request and always closed;
- message and user reads never return password hashes or raw stored secrets;
- security-sensitive changes append audit events.

## Production promotion gate

This API is not connected to the live dashboard or agents yet. Promotion requires:

1. first-run bootstrap/installer flow;
2. HTTPS application-server packaging for Windows and Ubuntu;
3. agent registration/authentication and heartbeat endpoints;
4. incremental history and identity integration;
5. API concurrency and load tests;
6. backup, upgrade and rollback tests;
7. browser cookie adapter using Secure, HttpOnly and SameSite controls;
8. staging parity and pilot approval.
