## Summary

Describe the problem and the change. Link the related issue, if any.

## Change type

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking API or configuration change
- [ ] Database migration
- [ ] Security hardening
- [ ] Documentation or repository presentation
- [ ] Other: describe in the summary

## Behavior and compatibility

- [ ] The change preserves the shared 0.2.0 API contract, or the contract and all callers are updated.
- [ ] Tenant isolation, idempotency, retry, and at-least-once semantics are preserved or explicitly revised.
- [ ] Any breaking change is documented in `CHANGELOG.md`.
- [ ] Any new environment variable is documented in `.env.example`, `README.md`, and `docs/deployment.md`.

## Verification

List the exact checks you ran and their results. Include focused tests, PostgreSQL/Redis checks, migration checks, or dashboard checks as relevant.

- [ ] `uv run pytest` or the relevant focused tests pass.
- [ ] `uv run alembic check` passes when models or migrations changed.
- [ ] PostgreSQL behavior is covered when schema, locking, constraints, or claims changed.
- [ ] Redis behavior is covered when wake-ups or quotas changed.
- [ ] Dashboard `npm run typecheck` and `npm run build` pass when dashboard code changed.

## Security and operations

- [ ] No credentials, customer payloads, or absolute developer paths are included.
- [ ] Endpoint secrets and API keys are not exposed beyond one-time responses or server-side environment use.
- [ ] Outbound destinations remain public HTTP(S) only and redirects remain disabled.
- [ ] Dashboard credentials are server-only and never use a `NEXT_PUBLIC_` prefix.
- [ ] Migration rollout, backup, retention, and receiver-idempotency implications are documented when relevant.

## Screenshots or examples

Add redacted screenshots for UI changes and request/response examples for API changes. Remove this section if it does not apply.
