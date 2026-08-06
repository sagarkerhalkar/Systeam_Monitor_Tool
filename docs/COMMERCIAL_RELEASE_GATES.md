# Commercial Release Gates

The commercial product is released only from `commercial-v1` through a reviewed pull request and a signed release process. The live internal branch `workingcode` is not modified by commercial experiments.

## Mandatory pull-request gates

Every commercial pull request must pass:

1. Python compilation on Windows and Ubuntu runners.
2. Commercial unit, identity and migration tests on Python 3.12 and 3.14.
3. Dashboard JavaScript syntax validation.
4. Windows PowerShell agent syntax validation.
5. Ubuntu shell agent syntax validation.
6. Migration safety validation.
7. Verification that source is committed normally and no Base64/patch-injection workflow is used.

A failed or skipped mandatory job blocks merge.

## Mandatory release-candidate gates

Before a commercial release candidate can be promoted:

- no open P0 or P1 defect;
- identity, history, message delivery and database-maintenance tests pass;
- clean install, upgrade, repair, uninstall and rollback pass for Windows and Ubuntu packages;
- backup and restore are proven with retained customer data;
- security, dependency and secret scans pass;
- load tests pass at 100, 500 and 1,000 simulated agents;
- sustained soak testing shows no uncontrolled memory, database or WAL growth;
- release artifacts are checksummed and digitally signed;
- rollback artifacts and deployment evidence are attached to the release.

## Production safety

Production deployment is a separate approved action. CI must never rewrite production files or databases. Database migrations are versioned, additive by default, backed up before execution and verified after execution. Any failed health check triggers rollback rather than partial continuation.
