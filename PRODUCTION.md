# Deployment and release status

**Status: hardened single-clinic candidate; not approved for live patient use.**

The production entrypoint is `production:create_app`. It does not register the legacy demo, fixture, or unsigned legacy webhook routes. The local app remains available for development. Production uses real uploads and persistent SQLite records; it never substitutes example patient data.

## Install and configure

Use Python 3.14 in an isolated environment. Install `requirements.txt` and `requirements-ocr.txt`. Run `python verify.py --full` before deployment. OCR tests generate synthetic documents with Pillow's bundled font.

Supply secrets through the host's protected environment, not source control:

- `MEDAI_STAFF_KEYS`: JSON mapping each staff identifier to a different randomly generated token of at least 32 characters. Tokens are server-side secrets; give each user only their own token. Remove a mapping to revoke it, then restart all processes. The shared development token is ignored when this mapping is configured.
- `MEDAI_TENANT_ID`: one clinic identifier.
- `MEDAI_DB_PATH`: absolute path on private persistent storage. Use a separate database and process for each clinic. This is not a shared multi-clinic deployment.
- `MEDAI_ALLOWED_HOSTS`: comma-separated explicit hostnames, without schemes or wildcards.
- `MEDAI_ENABLE_LEGACY_DEMO=false`.
- `CALLE_ENABLE_LIVE_CALLS=false` until release validation is complete.

Run one server process behind a TLS reverse proxy:

```text
python -m uvicorn production:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Use the host's service manager to restart the process on failure. Keep port 8000 private. The proxy must preserve Host, enforce HTTPS, limit bodies to 10 MB and request durations, and omit webhook URLs and bodies from logs: webhook paths contain capability tokens. Do not expose the development server or run multiple OCR workers without revisiting concurrency and resource limits.

The production health endpoint checks database availability. Authenticated `/local/readiness` reports call configuration separately; configuration is not evidence of delivery. No health/readiness endpoint contacts a provider.

## Operations

Record writes append an audit entry with timestamp, staff/system identity, tenant, record ID and content digest. Audit entries are transactionally committed with the data. This is an operational audit trail, not tamper-proof logging. Protect filesystem access and export backups to access-controlled storage.

Create a consistent SQLite backup, choosing a new destination each time:

```text
python operations.py ABSOLUTE_DATABASE_PATH ABSOLUTE_NEW_BACKUP_PATH
```

The tool uses SQLite's online backup API, verifies integrity and refuses to overwrite files. For restore, stop server and worker, restore into a new path, set MEDAI_DB_PATH to that path, run health and review records, then restart. Never restore an old call budget or dispatch state and immediately enable calling: reconcile any calls created after the backup first. Backup restoration is covered by offline tests.

Apply encrypted disks, least-privilege filesystem access, and the clinic's backup retention/deletion policy on the chosen host. These host controls are not implemented by application code and have not been verified here. Original prescription bytes, OCR text, draft fields, confidence values and source hashes are retained in the database for authenticated staff review. Include these records in the clinic's retention and backup policy.

## Calling and OCR release gates

- The earlier 404 connection failure is resolved. One authorized confirmation call completed end to end on 2026-09-11 (`call_wO03KFjpByysRKrRHo4abg`): identity check, single-medication `en-IN` readback, patient confirmation, and a conforming structured result. Delivery is not yet dependable — three of four authorized attempts to that number failed at the carrier before conversation — and this is one call on one number, so live calling must remain disabled pending the gates below.
- Still to demonstrate before calling is released: real callback delivery to a public HTTPS endpoint (the verified call used a placeholder URL and was resolved by reconciliation), duplicate-event replay against a real provider event, the correction/review path, multi-medication readback, and the reminder/caregiver flows. Real call testing consumes credits and needs advance notice.
- `POST /local/confirmations/{call_id}/reconcile` resolves a submitted call from the provider's own record when no callback can arrive. It shares the webhook's outcome rules, places no call and spends no budget. It is a reconciliation aid, not a substitute for verified callback delivery, and cannot recover a dispatch whose provider call ID was never returned.
- Current callbacks use random per-call capabilities, not provider signatures. Review whether that authentication model meets the deployment's requirements; do not claim cryptographic provider verification.
- OCR performs real local text recognition; conservative source-derived drafts assist staff, who fill missing fields and verify every medication value. Handwritten and non-English prescription accuracy is not validated. No automatic medication interpretation is promised.
- Test with representative, authorized prescription samples before patient use, including unreadable scans. Stop at staff review for uncertain values.
- Named bearer tokens are suitable only for a controlled deployment whose access policy accepts them. Public multi-clinic use requires a separate identity/role/session design and tenant isolation architecture.
- Deployment destination, TLS configuration, supervised service setup, backup schedule/retention, host encryption and staff access policy are still unconfirmed. There has been no deployment, commit or push.
