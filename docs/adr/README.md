# Architecture Decision Records

Short records of significant, hard-to-reverse decisions, in the format
*Context → Decision → Consequences*. Add a new numbered file rather than editing an
accepted ADR. To change a decision, write a new ADR that supersedes the old one.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-modular-monolith-with-async-workers.md) | Modular monolith with asynchronous workers | Accepted |
| [0002](0002-repository-layout.md) | Repository layout: one backend codebase for API and worker | Accepted |
| [0003](0003-synchronous-sqlalchemy-with-psycopg.md) | Synchronous SQLAlchemy 2 with psycopg 3 | Accepted |
| [0004](0004-dependency-and-tooling-choices.md) | Dependency management and code-quality tooling | Accepted |
| [0005](0005-frontend-to-backend-communication.md) | Frontend reaches the API through a same-origin server route | Accepted |
| [0006](0006-object-storage-minio-image.md) | MinIO image source for local object storage | Accepted |
| [0007](0007-ai-provider-abstraction.md) | AI provider abstraction (Gemini in V1) | Accepted (revised) |
| [0008](0008-authentication-sessions.md) | Server-side sessions in HttpOnly cookies | Accepted |
| [0009](0009-tenant-isolation.md) | Tenant isolation in the service layer, proven by tests | Accepted |
| [0010](0010-deterministic-risk-engine-ai-advisory.md) | Deterministic risk engine is authoritative; AI is advisory | Accepted |
| [0011](0011-tamper-evident-audit-trail.md) | Tamper-evident, append-only audit trail | Accepted |
| [0012](0012-google-cloud-readiness.md) | Google Cloud readiness without provisioning | Accepted |
