# Build the Invoice Risk & Payment Control OS — End-to-End

You are the lead engineer responsible for implementing this product end-to-end in the existing repository.

You must treat this as a serious production-oriented SaaS application, not a demo or prototype.

The goal is to build a complete, locally runnable, tested, documented MVP that is architecturally ready to be deployed to Google Cloud later.

Do NOT provision or deploy Google Cloud infrastructure during this task.

Use local Docker Compose for development and testing.

---

# 1. PRODUCT

Product name:

**Invoice Risk & Payment Control OS**

Core positioning:

> Every invoice gets checked before your business pays it.

Alternative positioning:

> The payment firewall for your business.

The product is an India-first B2B financial-control SaaS.

The core workflow is:

```text
Invoice arrives
      ↓
Invoice is ingested
      ↓
Document/data extracted
      ↓
Vendor identified
      ↓
PO matched when available
      ↓
Historical/vendor context checked
      ↓
Deterministic risk rules executed
      ↓
Gemini-assisted contextual analysis
      ↓
Risk signals combined
      ↓
Invoice assigned a review status
      ↓
Human reviewer investigates
      ↓
Approve / Reject / Request changes
      ↓
Complete audit trail
```

The system is designed to prevent:

* Duplicate invoices
* Vendor impersonation
* Suspicious bank-account changes
* PO mismatches
* Quantity mismatches
* Price anomalies
* Tax/GST arithmetic inconsistencies
* Missing invoice information
* New/unusual vendor behavior
* Suspicious invoice patterns
* Split invoices
* Unexpected vendor behavior
* Other financially relevant anomalies

The system must provide explainable evidence for every material risk signal.

---

# 2. CRITICAL PRODUCT PRINCIPLE

This is NOT an "AI invoice processing" application.

OCR/document extraction is only one component.

The core product is:

**financial risk detection + control + review + auditability**

Gemini is an assistant to the control system.

Gemini must NOT independently make irreversible financial decisions.

Do not build:

* Automatic payment execution
* Automatic bank transfers
* Autonomous approval of risky invoices
* Autonomous rejection based solely on an LLM
* LLM-controlled financial calculations
* LLM-controlled authorization

Human approval remains the control point.

---

# 3. TARGET ARCHITECTURE

Use a **modular monolith**.

Do NOT introduce microservices.

Do NOT introduce Kubernetes.

Do NOT introduce Kafka.

Do NOT introduce unnecessary distributed infrastructure.

The architecture should be:

```text
                    Browser
                       |
                       v
              +----------------+
              |    Next.js     |
              |   TypeScript   |
              +-------+--------+
                      |
                      | HTTP API
                      v
              +----------------+
              |    FastAPI     |
              |     API        |
              +-------+--------+
                      |
       +--------------+---------------+
       |              |               |
       v              v               v
 PostgreSQL         Redis          Object Storage
       |              |               |
       |              v               |
       |          Celery Worker       |
       |              |               |
       +--------------+---------------+
                      |
                      v
                  Gemini API
```

Production target:

```text
Next.js
   ↓
Google Cloud Run

FastAPI
   ↓
Google Cloud Run

Workers
   ↓
Cloud Run / appropriate managed compute

PostgreSQL
   ↓
Cloud SQL

Redis
   ↓
Memorystore

Object storage
   ↓
Google Cloud Storage

Containers
   ↓
Artifact Registry

Secrets
   ↓
Secret Manager

Observability
   ↓
Cloud Logging / Monitoring / Trace
```

Do not provision these production resources now.

The code must simply be compatible with this future deployment architecture.

---

# 4. TECHNOLOGY STACK

## Frontend

Use:

* Next.js
* TypeScript
* strict TypeScript
* App Router
* Tailwind CSS
* a reusable component system
* React testing infrastructure
* ESLint
* production build verification

Do not use JavaScript for application code.

---

# 5. BACKEND

Use:

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* Alembic
* PostgreSQL

Follow a clean modular architecture.

Do not put business logic directly inside route handlers.

Use services/use-cases/domain modules where appropriate.

---

# 6. BACKGROUND PROCESSING

Use:

* Celery
* Redis

Long-running operations must not block HTTP requests.

Examples:

* Invoice processing
* Document extraction
* Risk analysis
* Email ingestion
* Notification generation
* Other asynchronous work

Use explicit task boundaries.

Tasks must be observable and retryable where appropriate.

Avoid uncontrolled infinite retries.

---

# 7. OBJECT STORAGE

Local development:

**MinIO**

Production-compatible abstraction:

**S3-compatible/object-storage interface**

The application should not hard-code MinIO-specific business logic.

Files should be referenced through storage abstractions.

Production migration should be straightforward to Google Cloud Storage.

---

# 8. AI

Use **Gemini API**.

Do NOT use Anthropic.

Do NOT hard-code Gemini calls throughout the application.

Create an abstraction similar to:

```python
class AIProvider(Protocol):
    ...
```

and an implementation such as:

```text
GeminiProvider
```

Also create:

```text
MockAIProvider
```

for automated tests.

All application code that needs AI capabilities should depend on the abstraction rather than directly importing the Gemini SDK.

Environment variable:

```text
GEMINI_API_KEY
```

Never commit the key.

Never hard-code credentials.

Never print API keys in logs.

---

# 9. AI RESPONSIBILITIES

Gemini may be used for:

* Document understanding
* Difficult invoice extraction
* Contextual invoice interpretation
* Risk explanation
* Evidence summarization
* Anomaly/context signals
* Reviewer assistance
* Email/document interpretation

Gemini must NOT be trusted for:

* Financial arithmetic
* Tax arithmetic
* Duplicate determination
* Authorization
* Payment execution
* Final approval
* Tenant authorization
* Security decisions

Whenever deterministic logic can reliably perform a task, prefer deterministic logic.

---

# 10. DATABASE

Use PostgreSQL.

Use SQLAlchemy models.

Use Alembic migrations.

Do NOT rely on automatic table creation in production code.

The migration workflow must be reproducible.

Design the schema around multi-tenancy from the beginning.

At minimum, expect concepts such as:

```text
Organization
User
Membership
Role
Vendor
VendorBankAccount
PurchaseOrder
PurchaseOrderLine
Invoice
InvoiceLine
InvoiceDocument
RiskSignal
RiskAssessment
Review
Approval
AuditEvent
Notification
```

You may introduce additional entities where necessary.

Do not prematurely over-model the system.

---

# 11. MULTI-TENANCY

This is a SaaS application.

Tenant isolation is a security boundary.

Every tenant-owned resource must be associated with an organization/tenant.

The application must never rely on the frontend to enforce tenant boundaries.

Authorization must be enforced server-side.

Tests must explicitly verify:

```text
Organization A cannot access Organization B's data.
```

This must cover:

* Vendors
* Invoices
* Documents
* Purchase orders
* Reviews
* Risk information
* Audit logs
* Notifications
* Other tenant-owned objects

Do not leave tenant isolation as a future TODO.

---

# 12. AUTHENTICATION

Implement secure application authentication.

Users should be able to:

* Sign up/in
* Sign out
* Maintain authenticated sessions
* Belong to organizations
* Have roles

Do not store plaintext passwords.

Use secure password hashing.

Implement appropriate session/token expiration.

Protect authenticated API routes.

Avoid putting sensitive authentication information into client-side storage unnecessarily.

Add authentication tests.

---

# 13. RBAC

Implement role-based access control.

At minimum support roles appropriate for:

```text
Owner
Admin
Reviewer
Viewer
```

You may refine the permission model where necessary.

Permissions must be enforced in the backend.

Do not rely on hiding UI buttons as authorization.

For example:

```text
Viewer
    cannot approve invoices

Reviewer
    can review invoices
    can provide review decisions

Admin
    can manage organization configuration

Owner
    has organization-level administrative control
```

Document the final permission matrix.

---

# 14. VENDOR MANAGEMENT

Implement vendor management.

Users should be able to:

* Create vendors
* Edit vendors
* View vendor details
* Search vendors
* View vendor history
* Store GST-related information
* Store contact information
* Store payment/bank information
* View vendor risk-related information

Track bank-account changes as historical events.

Do not simply overwrite sensitive vendor banking information without an audit trail.

A bank-account change must be treated as a security-relevant event.

---

# 15. INVOICE INGESTION

Support invoice ingestion through:

1. Manual upload
2. Invoice link import where safely supported
3. Email ingestion architecture

For the initial implementation, manual upload must be fully functional.

Accepted document types should be explicitly defined.

Store the original document.

Create processing metadata.

Track processing state.

Example:

```text
uploaded
↓
queued
↓
processing
↓
extracted
↓
risk_analysis
↓
review_required
↓
approved / rejected / needs_changes
```

Failures must be represented explicitly.

Do not silently swallow processing errors.

---

# 16. SECURE URL IMPORT

If importing invoices from URLs:

The server must fetch the resource safely.

Protect against:

* SSRF
* localhost access
* private network access
* internal service access
* unsafe redirects
* oversized responses
* excessive connection time
* unsupported protocols

Validate addresses at connection time.

Revalidate after redirects.

Limit:

* response size
* request duration
* redirects

Do not expose internal network access through this feature.

---

# 17. INVOICE EXTRACTION

Build an extraction pipeline.

Extract information such as:

```text
Vendor
Vendor GSTIN
Invoice number
Invoice date
Due date
Currency
Subtotal
Tax
GST components
Total
PO number
Line items
Quantity
Unit price
Tax rate
Bank/payment details when present
```

Extraction must preserve provenance.

The system should distinguish:

```text
value
confidence
source
```

where appropriate.

For example:

```text
invoice_number
value = INV-1029
source = document
confidence = ...
```

Do not fabricate missing values.

Unknown values should remain unknown.

---

# 18. PURCHASE ORDERS

Implement purchase orders.

Users should be able to:

* Create POs
* Add PO line items
* Associate POs with vendors
* View PO status
* Associate invoices with POs

Support matching:

```text
Invoice
    ↕
Purchase Order
```

Where possible, compare:

* Vendor
* Quantity
* Unit price
* Total
* PO number
* Line items

Do not let an LLM decide mathematical equality.

Use deterministic comparison.

---

# 19. RISK ENGINE

This is one of the most important parts of the product.

Build a deterministic risk engine.

Risk rules should be modular.

Example rule categories:

```text
Duplicate invoice
Vendor mismatch
PO mismatch
Quantity mismatch
Price mismatch
Unexpected price increase
GST/tax inconsistency
Missing required information
Bank-account change
New vendor
Unusual invoice amount
Unusual frequency
Invoice splitting
Historical anomaly
```

Do not put all rules into one giant function.

Create independently testable rules.

Each rule should produce explainable output.

Example:

```json
{
  "rule": "duplicate_invoice",
  "severity": "high",
  "status": "triggered",
  "evidence": [
    "Same vendor",
    "Same invoice number",
    "Same total amount"
  ]
}
```

Risk output must be explainable.

---

# 20. DETERMINISTIC FINANCIAL LOGIC

All financial calculations must use deterministic code.

Do NOT ask Gemini:

> "Is 18% GST correctly calculated?"

Calculate it in code.

Do NOT ask Gemini:

> "Are these invoice totals equal?"

Calculate it in code.

Use appropriate decimal handling.

Avoid floating-point arithmetic for financial values.

Test:

* tax calculations
* totals
* rounding
* quantities
* unit prices
* currency values
* matching tolerances

Document the rules.

---

# 21. DUPLICATE DETECTION

Implement multiple duplicate signals where practical.

Potential signals:

```text
Vendor
Invoice number
Invoice date
Amount
Document hash
PO
Line items
```

Use deterministic matching.

Support exact and configurable similarity logic where justified.

Do not rely exclusively on embeddings or an LLM.

---

# 22. VENDOR BANK ACCOUNT CHANGES

Treat bank-account changes as high-sensitivity events.

Track:

```text
previous value
new value
timestamp
actor/source
verification state
```

Do not silently update payment information.

Generate a risk signal when appropriate.

The system must make such changes visible to reviewers.

---

# 23. GEMINI RISK ASSISTANCE

Gemini may analyze structured evidence produced by deterministic rules.

For example:

```text
Deterministic evidence
        ↓
Gemini
        ↓
Contextual explanation
```

Gemini should return structured output.

Use schema validation.

Do not trust arbitrary natural-language output as application logic.

Validate model responses before persisting or displaying them.

Prompt injection defenses must be considered because invoice documents are untrusted input.

Never allow document content to override system instructions.

Treat all invoice text as untrusted data.

---

# 24. HUMAN REVIEW

Build an invoice review interface.

Reviewer should see:

* Original invoice
* Extracted fields
* Vendor
* PO
* Matching results
* Risk signals
* Evidence
* Gemini explanation
* Audit history
* Previous reviews where appropriate

Reviewer actions:

```text
Approve
Reject
Request Changes
Mark Risk Accepted / Override where authorized
```

Every decision must record:

```text
user
timestamp
decision
reason
relevant evidence
```

Do not allow silent state changes.

---

# 25. APPROVAL WORKFLOW

Implement configurable approval logic at a sensible MVP level.

Example:

```text
Low risk
   ↓
Review

Medium/high risk
   ↓
Additional review

High-value/high-risk invoice
   ↓
Approver required
```

Do not overbuild enterprise workflow configuration.

Focus on a coherent V1.

No payment execution.

---

# 26. AUDIT LOG

Auditability is a core feature.

Create immutable-style audit records for security/business events.

Track events such as:

* Login
* Logout where appropriate
* Vendor creation
* Vendor modification
* Bank-account change
* Invoice upload
* Invoice modification
* PO modification
* Risk assessment
* Review
* Approval
* Rejection
* Override
* User/role changes
* Organization configuration changes

Audit events should contain sufficient metadata to reconstruct what happened.

Audit logs must be tenant-isolated.

Users must not be able to arbitrarily edit historical audit records through the application.

---

# 27. NOTIFICATIONS

Implement the notification foundation.

At minimum support an internal notification model.

Design for future:

* Email
* Slack
* Other channels

Do not spend excessive time building a complex notification platform.

Focus on the core workflow.

---

# 28. EMAIL INGESTION

Build the architecture for invoice email ingestion.

The system should be designed so that invoices received through a dedicated mailbox can eventually enter the same processing pipeline as uploaded invoices.

Do not create unnecessary dependence on one email provider.

The pipeline should conceptually be:

```text
Email
 ↓
Attachment extraction
 ↓
Document storage
 ↓
Invoice ingestion
 ↓
Extraction
 ↓
Risk engine
 ↓
Review
```

If a real email provider integration is not appropriate for local development, provide a mock/local ingestion mechanism and a clean provider abstraction.

---

# 29. DASHBOARD

Build a useful SaaS dashboard.

Show information such as:

```text
Invoices received
Invoices requiring review
High-risk invoices
Approved
Rejected
Pending
Potential duplicate invoices
Potential savings / prevented leakage
Vendor risk indicators
Recent activity
```

Do not fabricate financial savings.

If a metric cannot be reliably calculated, label it clearly or omit it.

---

# 30. ANALYTICS

Provide basic analytics.

Examples:

* Invoice volume
* Review volume
* Risk categories
* Risk severity distribution
* Vendor anomalies
* Approval/rejection counts
* Review turnaround time
* Duplicate detections
* PO mismatch counts

Make queries efficient enough for the expected MVP workload.

Avoid premature data warehousing.

---

# 31. SECURITY

Treat security as a first-class concern.

Implement:

* Input validation
* Authentication
* Authorization
* Tenant isolation
* Secure password hashing
* Secure sessions/tokens
* CSRF protection where applicable
* CORS configuration
* Rate limiting where appropriate
* Secure headers
* File type validation
* File size limits
* Safe file names
* SSRF protection
* SQL injection prevention through ORM/query parameterization
* XSS-conscious rendering
* Secrets management
* Safe logging
* No credentials in source control
* No sensitive information in error responses

Do not claim security is complete merely because these features exist.

Document known limitations.

---

# 32. FILE SECURITY

Uploaded documents are untrusted.

Implement reasonable protections for:

* MIME type
* extension
* file size
* malformed files
* dangerous filenames
* storage isolation

Do not execute uploaded files.

Do not treat uploaded content as trusted instructions.

---

# 33. OBSERVABILITY

Implement structured application logging.

Logs should make it possible to diagnose:

* request failures
* background task failures
* invoice processing failures
* AI failures
* storage failures
* database failures

Never log:

* passwords
* API keys
* authentication secrets
* unnecessary banking information
* sensitive invoice contents

Prepare the logging architecture for Google Cloud Logging.

---

# 34. ERROR HANDLING

Build consistent API errors.

Do not expose stack traces to end users.

Errors should include useful identifiers/codes where appropriate.

Background jobs must record failures.

AI failures should degrade gracefully.

For example:

```text
Gemini unavailable
       ↓
Deterministic risk engine still runs
       ↓
Invoice remains reviewable
       ↓
Reviewer sees that AI assistance was unavailable
```

The AI layer must not become a single point of failure for financial control.

---

# 35. TESTING

Testing is mandatory.

Implement:

### Backend unit tests

For:

* Risk rules
* Financial calculations
* Duplicate detection
* PO matching
* Vendor logic
* Permissions
* Tenant isolation
* Authentication
* Audit events

### Integration tests

For:

* Database
* API
* Celery
* Redis
* Storage
* Invoice processing pipeline

### Frontend tests

For important:

* Forms
* Authentication flows
* Invoice review
* Risk display
* Approval actions

### End-to-end tests

Implement the most important end-to-end workflow:

```text
Create organization
 ↓
Create user
 ↓
Create vendor
 ↓
Upload invoice
 ↓
Process invoice
 ↓
Run risk analysis
 ↓
Review invoice
 ↓
Approve/reject
 ↓
Verify audit trail
```

Do not make tests dependent on real Gemini API calls.

Use `MockAIProvider`.

---

# 36. GEMINI TESTING

Real Gemini calls must NOT run during normal automated tests.

Use:

```text
MockAIProvider
```

Tests must cover:

* Valid Gemini response
* Invalid structured response
* Timeout
* API failure
* Empty response
* Malformed output
* Prompt-injection-like document content

The application should handle AI failures safely.

---

# 37. DOCKER

The entire local system must run with Docker Compose.

Expected services should include approximately:

```text
frontend
api
worker
postgres
redis
minio
```

Add other services only when justified.

The developer should be able to run something equivalent to:

```bash
docker compose up --build
```

and start the application.

Provide health checks.

Ensure services start in a sensible order.

Do not rely on manually installed host dependencies unnecessarily.

---

# 38. CONFIGURATION

Use environment variables.

Provide:

```text
.env.example
```

Never commit:

```text
.env
```

or secrets.

Configuration should distinguish:

```text
development
test
production
```

without duplicating business logic.

Include:

```text
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_*
GEMINI_API_KEY
AUTH_SECRET
```

and any other required configuration.

Document each variable.

---

# 39. CI/CD

Create GitHub Actions workflows.

At minimum:

```text
Backend:
- install
- lint
- type check
- tests

Frontend:
- install
- lint
- type check
- tests
- build

Repository:
- security-sensitive checks where appropriate
```

CI must not require a real Gemini API key.

Use mocks.

Do not implement production deployment to GCP yet unless explicitly requested later.

---

# 40. GOOGLE CLOUD COMPATIBILITY

Although we are not deploying yet, design the application for future Google Cloud deployment.

Production target:

```text
Frontend → Cloud Run
API → Cloud Run
Workers → Cloud Run / appropriate managed compute
PostgreSQL → Cloud SQL
Redis → Memorystore
Files → Cloud Storage
Images → Artifact Registry
Secrets → Secret Manager
Logs → Cloud Logging
Metrics → Cloud Monitoring
Tracing → Cloud Trace
```

Do not hard-code local infrastructure assumptions.

For example:

BAD:

```python
"/tmp/minio/something"
```

GOOD:

```text
StorageProvider
```

with local and production implementations/configurations.

Similarly:

```text
Database
Redis
Storage
AI
Email
```

should have clear configuration boundaries.

---

# 41. API DESIGN

Use versioned APIs where appropriate.

Example:

```text
/api/v1/...
```

Maintain consistent naming.

Use Pydantic schemas for request/response validation.

Do not expose raw database models directly as public API contracts.

Generate/update API documentation.

---

# 42. FRONTEND UX

The UI should feel like a serious B2B SaaS application.

Required areas:

```text
Login
Dashboard
Invoices
Invoice Review
Vendors
Purchase Orders
Risk
Approvals
Notifications
Audit Log
Settings
Organization/User Management
```

Prioritize clarity over visual complexity.

The primary user should quickly understand:

```text
What needs my attention?
Why is it risky?
What evidence supports that?
What action can I take?
```

Avoid unnecessary animations and decorative complexity.

---

# 43. PRODUCT SAFETY

Do not make claims such as:

* "This invoice is fraudulent"
* "This vendor is fraudulent"

unless the system is explicitly representing a verified external fact.

Prefer:

```text
Potential duplicate detected
Potential bank-account change
PO mismatch detected
Unusual amount
High-risk signal
Requires review
```

The system detects risk signals; humans make consequential judgments.

---

# 44. DATA PROVENANCE

Where possible, every important extracted/risk field should have provenance.

For example:

```text
Invoice total
  → extracted from invoice

PO total
  → sourced from purchase order

Risk signal
  → generated by rule X

AI explanation
  → generated by Gemini
```

Do not blur deterministic facts and AI-generated interpretations.

---

# 45. DOCUMENTATION

Create and maintain:

```text
README.md

docs/
├── architecture.md
├── product-overview.md
├── development.md
├── security.md
├── database.md
├── api.md
├── ai.md
├── risk-engine.md
├── deployment-gcp.md
├── testing.md
├── adr/
└── ...
```

Document important architectural decisions as ADRs.

Do not create documentation that claims features exist when they do not.

---

# 46. DEVELOPMENT PRINCIPLES

Follow these principles throughout the implementation:

1. Prefer simple architecture.
2. Prefer deterministic logic over LLM logic when possible.
3. Keep modules cohesive.
4. Avoid premature abstraction.
5. Avoid premature microservices.
6. Avoid unnecessary dependencies.
7. Keep secrets out of source control.
8. Validate untrusted input.
9. Treat tenant isolation as a security boundary.
10. Make important operations auditable.
11. Make failures observable.
12. Write tests alongside implementation.
13. Keep production migration in mind.
14. Do not silently swallow errors.
15. Do not fabricate data.
16. Do not claim something works without testing it.

---

# 47. IMPLEMENTATION ORDER

Build the application in these phases.

## Phase 0 — Product foundation

Confirm:

* Customer/problem definition
* Product promise
* V1 scope
* V1 exclusions
* Success metrics
* Pilot assumptions

Document them.

Do not spend excessive time on business speculation.

---

## Phase 1 — Engineering foundation

Complete:

* Repository structure
* Next.js
* TypeScript
* FastAPI
* PostgreSQL
* SQLAlchemy
* Alembic
* Redis
* Celery
* MinIO
* Docker Compose
* Environment configuration
* Logging
* Health/readiness endpoints
* AIProvider abstraction
* GeminiProvider boundary
* MockAIProvider
* Testing foundation
* CI
* Documentation

Verify everything.

---

## Phase 2 — SaaS core

Implement:

* Authentication
* Organizations
* Memberships
* RBAC
* Tenant isolation
* User management
* Organization settings

Add tests.

---

## Phase 3 — Vendors

Implement:

* Vendor CRUD
* Vendor details
* GST information
* Bank/payment information
* Vendor history
* Bank-account change events
* Vendor-level audit trail

Add tests.

---

## Phase 4 — Invoice ingestion

Implement:

* Upload
* Storage
* Processing pipeline
* Invoice entity
* Invoice documents
* Extraction pipeline
* Gemini integration
* Provenance
* Processing states
* Failure handling

Add tests.

---

## Phase 5 — Purchase orders

Implement:

* PO CRUD
* PO lines
* Vendor association
* Invoice association
* Deterministic matching

Add tests.

---

## Phase 6 — Risk engine

Implement:

* Duplicate detection
* Vendor mismatch
* PO mismatch
* Quantity mismatch
* Price mismatch
* Tax/GST checks
* Bank-account change risk
* New vendor risk
* Unusual amount
* Other justified V1 rules

Implement explainable risk signals.

Add extensive tests.

---

## Phase 7 — Human review and approval

Implement:

* Review queue
* Invoice review page
* Risk evidence
* AI explanation
* Reviewer decisions
* Approval workflow
* Rejection
* Request changes
* Overrides where authorized
* Complete audit trail

Add tests.

---

## Phase 8 — Notifications

Implement the notification foundation and useful MVP notifications.

---

## Phase 9 — Email ingestion

Implement the provider abstraction and local/mock email ingestion flow.

Do not overbuild provider-specific infrastructure.

---

## Phase 10 — Dashboard and analytics

Implement:

* Dashboard
* Invoice metrics
* Risk metrics
* Review metrics
* Vendor risk information
* Recent activity

Only display metrics backed by real data.

---

## Phase 11 — Audit and compliance infrastructure

Harden:

* Audit logs
* Event provenance
* Data access boundaries
* Security-sensitive actions
* Retention/configuration foundations where appropriate

---

## Phase 12 — Security hardening

Perform a security review.

Specifically test:

* Tenant isolation
* Authorization bypass
* SSRF
* File upload abuse
* Authentication
* Session handling
* Injection
* XSS
* CSRF where applicable
* Secrets exposure
* Sensitive logging
* Prompt injection
* AI output validation

Fix identified issues.

---

## Phase 13 — Production architecture readiness

Prepare:

* Docker production images
* Configuration separation
* Cloud-compatible storage abstraction
* Cloud-compatible database configuration
* Cloud-compatible Redis configuration
* Secret configuration
* Logging
* Health checks
* Graceful shutdown
* Worker behavior
* Resource configuration

Do NOT provision GCP resources.

Create:

```text
docs/deployment-gcp.md
```

explaining the eventual deployment architecture.

---

## Phase 14 — Production testing

Run:

* Unit tests
* Integration tests
* E2E tests
* Build tests
* Docker Compose clean-start
* Migration tests
* Permission tests
* Tenant-isolation tests
* Failure-path tests
* AI failure tests
* Security checks

Fix failures.

---

## Phase 15 — Pilot readiness

Create:

* Pilot workflow
* Demo data/seeding strategy
* Pilot documentation
* Admin/operator documentation
* Known limitations
* Measurement framework

The application must be usable by a real pilot customer locally/staging-ready.

---

## Phase 16 — V1 release candidate

Perform a final audit.

Verify:

```text
Product
Architecture
Security
Data isolation
AI
Risk engine
Testing
UX
Documentation
Docker
CI
Cloud compatibility
```

Create:

```text
docs/v1-release-audit.md
```

with:

```text
PASS
FAIL
PARTIAL
NOT VERIFIED
```

for every major requirement.

---

# 48. VERY IMPORTANT: DO NOT FAKE COMPLETION

Never mark a requirement complete simply because code exists.

For every important feature:

```text
Implement
   ↓
Test
   ↓
Verify
   ↓
Document
   ↓
Mark complete
```

If something cannot be verified, explicitly write:

```text
NOT VERIFIED
```

Do not say:

```text
Done
```

without evidence.

---

# 49. GIT DISCIPLINE

Use meaningful commits.

Prefer commits representing coherent milestones such as:

```text
feat(auth): implement authentication
feat(vendors): add vendor management
feat(invoices): add invoice ingestion
feat(risk): implement duplicate detection
feat(review): add invoice review workflow
test(risk): add risk engine coverage
fix(auth): prevent cross-tenant access
docs: update architecture
```

Do not create meaningless commits for every tiny change.

Do not commit secrets.

---

# 50. FINAL ACCEPTANCE CRITERIA

The project is complete only when all of the following are true.

## Product

* Core invoice-risk workflow works end-to-end.
* Human review is implemented.
* Risk signals are explainable.
* No automatic payment execution exists.
* AI is assistive, not authoritative.

## Engineering

* Frontend builds.
* Backend starts.
* Database migrations work.
* Redis works.
* Celery works.
* MinIO works.
* Gemini integration works when configured.
* Mock Gemini works in tests.
* Docker Compose works from a clean environment.

## Security

* Authentication works.
* RBAC works.
* Tenant isolation is tested.
* File uploads are protected.
* SSRF protections exist for URL import.
* Secrets are not committed.
* Sensitive information is not unnecessarily logged.

## Testing

* Unit tests pass.
* Integration tests pass.
* E2E workflow passes.
* Frontend tests pass.
* CI passes.
* No real Gemini API call is required by CI.

## Documentation

Documentation accurately describes the implementation.

## Cloud readiness

The architecture can be migrated to:

```text
Cloud Run
Cloud SQL
Memorystore
Cloud Storage
Artifact Registry
Secret Manager
Cloud Logging
Cloud Monitoring
Cloud Trace
```

without rewriting the application architecture.

---

# 51. FINAL RULE: WORK AUTONOMOUSLY BUT SAFELY

You are authorized to implement the product across the repository.

Inspect the existing repository before modifying it.

Reuse existing good code where appropriate.

Do not destroy working functionality unnecessarily.

If the existing repository contradicts this specification, preserve useful existing work and adapt the architecture rather than blindly deleting it.

When a design decision is ambiguous, choose the simplest production-sensible approach consistent with this specification and document the decision.

Do not stop after creating scaffolding.

Do not stop after implementing only the backend.

Do not stop after implementing only the UI.

Continue through the phases until the complete MVP is implemented and verified.

However:

**Do not deploy to Google Cloud yet.**

The goal of this task is:

```text
Existing repository
       ↓
Complete Invoice Risk & Payment Control OS
       ↓
Tested
       ↓
Audited
       ↓
Documented
       ↓
Dockerized
       ↓
Google-Cloud-ready
       ↓
STOP
```

At the very end, produce:

```text
docs/final-build-report.md
```

containing:

1. What was implemented
2. Architecture summary
3. Database summary
4. API summary
5. Frontend summary
6. Risk-engine summary
7. Gemini integration summary
8. Security summary
9. Testing summary
10. Docker summary
11. CI summary
12. GCP-readiness summary
13. Known limitations
14. Technical debt
15. Items intentionally excluded from V1
16. Final PASS/FAIL/PARTIAL/NOT VERIFIED status for each major phase

Do not begin Google Cloud deployment.

Stop only after the final local V1 audit is complete.
