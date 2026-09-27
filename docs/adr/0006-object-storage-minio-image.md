# 0006 - MinIO image source for local object storage

- Status: Accepted
- Date: 2026-09-27

## Context

The brief calls for MinIO as local S3-compatible storage. On 2026-09-27:

- `docker pull minio/minio:latest` fails: the repository no longer exists on Docker Hub.
- `quay.io/minio/minio` returns `401 UNAUTHORIZED`.
- `bitnami/minio` is not available either.
- `cgr.dev/chainguard/minio:latest` is available. It is built from MinIO source
  (RELEASE.2026-09-22T19-25-18Z at the time of writing, AGPLv3) and runs as non-root.

## Decision

Use `cgr.dev/chainguard/minio`, **pinned by digest** in `docker-compose.yml`. Create the
bucket from our own code (`python -m app.cli ensure-bucket`, run by the `init`
service), so no separate `mc` container is needed. The application talks to storage
only through the S3 API (boto3), so it is not coupled to MinIO.

## Consequences

- Chainguard's free tier publishes only `latest`, so the digest pin is what makes
  builds reproducible. Updating means pulling `latest` and replacing the digest.
- If this image disappears, any S3-compatible server can replace it (for example
  SeaweedFS or Garage, or a MinIO image built locally) by changing only the Compose
  service.
- Production will use a managed S3-compatible service, with India data residency to be
  decided in a later step. The code needs only different `S3_*` settings.
- MinIO is AGPLv3. It is used only as a local development dependency, unmodified and
  not distributed with the product. Review the licence before using it in any
  deployed environment.
