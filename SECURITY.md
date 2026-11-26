# Security policy

## Supported versions

Security fixes are provided for the latest 0.2.x release. Older releases are not supported; upgrade to the current release before reporting a version-specific issue.

| Version | Supported |
|---|---|
| 0.2.x | Yes |
| 0.1.x | No |

## Reporting a vulnerability

**Do not open a public GitHub issue for a suspected vulnerability.**

Use GitHub's [private vulnerability reporting](https://github.com/sajadxdp0/hookflow/security/advisories/new) to contact the maintainers privately. Include:

- The affected HookFlow version or commit.
- A clear description of the issue and its security impact.
- Reproduction steps or a minimal proof of concept.
- Relevant configuration, such as environment mode and whether Redis is enabled.
- Any logs or request samples, with credentials and personal data removed.

Please do not include live API keys, endpoint signing secrets, encryption keys, or customer payloads. Do not test against systems you do not own or have explicit permission to assess.

Maintainers will triage the report, ask for clarification when needed, and coordinate a fix and disclosure with the reporter. This project does not publish a guaranteed response-time SLA.

## Scope

Security concerns in the following areas are in scope:

- Authentication, authorization, and tenant isolation.
- API-key, admin-token, and endpoint-secret handling.
- Signature generation and verification guidance.
- Outbound destination validation and redirect behavior.
- Dashboard credential exposure.
- Dependency, container, migration, or deployment weaknesses introduced by this repository.

The following are operational limitations rather than vulnerabilities by themselves:

- Delivery is at-least-once and can duplicate receiver side effects.
- There is no exactly-once or global ordering guarantee.
- API keys do not expire, and the admin surface uses one shared token without per-operator roles or audit logs.
- Redis is required for replica-safe quotas; in-memory limits are per process.
- HookFlow does not terminate TLS, retain data automatically, or provide managed high availability.
- `/health`, `/ready`, and `/metrics` are unauthenticated and require network or proxy controls.

See the [security model](docs/security.md) and [deployment guide](docs/deployment.md) for the full operating assumptions.

## Safe harbor

Good-faith security research that respects authorization, avoids service disruption, protects user data, and follows this reporting process is welcome. Do not access, modify, or exfiltrate data belonging to others.
