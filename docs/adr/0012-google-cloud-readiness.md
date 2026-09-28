# 0012 - Google Cloud readiness without provisioning

- Status: Accepted
- Date: 2026-09-27

## Decision

Keep the application platform-neutral, with explicit seams for Google Cloud:

- **Storage:** a `StorageProvider` protocol with S3 (MinIO locally) and GCS (Application
  Default Credentials) implementations, selected by `OBJECT_STORAGE_BACKEND`.
- **Configuration:** only environment variables, with secrets injected from Secret Manager.
  Production refuses unsafe values.
- **Images:** honour `PORT`, shut down gracefully (uvicorn drain, Celery warm shutdown with
  `acks_late`) and run as non-root. Migrations run as a separate job. The worker can
  expose a health port for Cloud Run.
- **Logging:** JSON with `severity` and Cloud Trace correlation (`GOOGLE_CLOUD_PROJECT`).
- **Service-to-service:** the web proxy can mint Cloud Run identity tokens for a private API.

No Google Cloud resources are provisioned by this repository. `docs/deployment-gcp.md`
documents the steps and marks them NOT VERIFIED until they are executed.

## Consequences

- Moving to Cloud Run, Cloud SQL, Memorystore and GCS changes configuration, not code.
- Not yet done: OpenTelemetry spans, Memorystore TLS (`rediss://` with CA),
  Infrastructure-as-Code (Terraform), and a CI deployment pipeline.
