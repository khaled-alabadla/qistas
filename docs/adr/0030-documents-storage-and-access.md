# ADR-0030 — Documents: private storage, validated uploads, audited downloads

- **Status:** Accepted — 2026-09-09
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0008 (all staff see all), ADR-0009 (sensitive-field redaction),
  ADR-0018 (app layout), ADR-0019 (object-level authz), ADR-0020 (audit),
  ADR-0022 (soft-delete / no-hard-delete — `Document` is in the named set),
  ADR-0023 (Docker/PostgreSQL parity, libmagic note), spec §34–36, §46, §82 Phase 6.
- **Phase:** 6

## Context

Spec §34–36 + §82 Phase 6: a `Document` model that may belong to a Case / Client
(Contract / Invoice models do not exist yet), secure private storage, validated
upload, authorised + audited download, categories. "Documents are sensitive legal
records" (§34). Open questions:

1. Where and how are files stored, and how are they served?
2. How is a file validated when "never trust the uploaded filename" and "never
   trust client-provided MIME type alone" (§35) — and this environment has no
   `libmagic` (Windows host, no Docker)?
3. Versioning — §36 says "allow future versioning… do not build… unless required".
4. Are documents more restricted than the case they hang off?

## Decision

### Model — `documents.Document`

`name` (display name, **not** the filename) · `document_type` (a fixed
`DocumentCategory` `TextChoices` — pleading / contract / power_of_attorney /
judgment / evidence / correspondence / official / identity / financial / other —
stable legal vocabulary, like `HearingType`; a configurable table is a later
change if the office asks) · `description` · `file` (`FileField`, private
storage, see below) · `original_filename` (sanitised, for the download filename
and display) · `content_type` (the **detected** type, never the client's) ·
`size` (`PositiveBigIntegerField`) · `sha256` (hex — integrity + duplicate
detection; a hash, not content, so it is safe in the audit trail) · FK `case`
(SET_NULL) · FK `client` (SET_NULL) · `uploaded_by` / `updated_by` (SET_NULL) ·
`TimeStampedModel`.

- **`on_delete` for `case`/`client` = SET_NULL** (ADR-0022 — never CASCADE into a
  document). A document with both FKs null is an "office document" — still valid.
- **Soft-delete ("retire")** via `deleted_at` + `deleted_by`, set only by
  `documents.services.retire_document`. The row and the **file blob are kept**
  (legal record); the list filters `.alive()`; a retired document 404s
  everywhere except the admin. No hard-delete path in the app; admin
  `has_delete_permission = False`. A retention/GC policy is a Phase 14 concern.

### Storage — private, never web-served

- A dedicated `STORAGES["documents"]` entry:
  - dev/prod → `FileSystemStorage(location = MEDIA_ROOT/"documents")` with
    **`base_url = None`** so `.url` raises — the file can only be reached through
    the download view.
  - tests → `InMemoryStorage` (no disk writes, same as `STORAGES["default"]`).
- **`upload_to`** returns `f"{year}/{month}/{uuid4().hex}{ext}"` — the path is
  unpredictable (uuid4), carries no user-controlled segment (**no path
  traversal**), and the extension is the **validator's canonical** one, not the
  client's.
- `MEDIA_URL` / whitenoise / `django.views.static.serve` are **never** wired to
  the documents directory. `config/urls.py` adds no media route.
- **Download** = `documents.views.document_download` — `GET` (a download is a
  read; browsers and `<a href>` need GET), but gated by `LoginRequiredMiddleware`
  + `@require_capability(documents.view)` + `Document.objects.for_user()` scope
  (404 outside scope / retired) + `services.record_download` (audit). Streams via
  `FileResponse(..., as_attachment=True, filename=<safe original name>)` with the
  stored `content_type`; `Content-Disposition: attachment` (never `inline`).
  `X-Accel-Redirect` / `sendfile` offload is a Phase 6-or-later perf option
  (grill D5) — not needed at single-office scale.

### Upload validation — curated allowlist + magic bytes, no libmagic

`documents.validators.validate_upload(file)` (Arabic errors, raises
`forms.ValidationError`):

1. **Size** ≤ `settings.DOCUMENTS_MAX_UPLOAD_MB` (default 25).
2. **Magic bytes** — read the header and match against a small **curated
   signature table** for exactly the allowed families: PDF (`%PDF-`), PNG, JPEG,
   GIF, TIFF, ZIP container (`PK\x03\x04` → docx/xlsx/pptx), OLE2
   (`\xD0\xCF\x11\xE0…` → legacy doc/xls/ppt), RTF (`{\rtf`), and a **plain-text**
   heuristic (no NUL byte in the first 8 KB, decodes as UTF-8/Latin-1) for
   `.txt` / `.csv` / `.md`.
   - This is a **hand-rolled allowlist**, not `python-magic` — it needs no system
     library (works on the Windows editor host and Linux prod identically) and is
     *deny-by-default*: an unrecognised header is rejected, period. Switching to
     `libmagic` for a wider format set is a documented Phase 12/14 option; the
     validator's interface does not change.
3. **Extension agreement** — the client filename's extension must be in the
   detected family's allowed-extension set (defence in depth; both signals must
   agree). The stored path uses the **canonical** extension for the detected
   family, never the client's string.
4. Returns `ValidatedUpload(canonical_ext, content_type, size, sha256)` — the
   sha256 is streamed in chunks during the same pass; `file.seek(0)` after.

The `client`-supplied `Content-Type` header is **never** consulted.

### Versioning — designed for, not built (§36)

Phase 6 has **no file replacement** — it is not in the §82 Phase 6 scope, and
§36 says not to build it "unless required". A document's `file` is immutable once
uploaded; a new version = a new `Document` (upload again). The `uuid4` paths +
`sha256` + `original_filename` mean a future `DocumentVersion` table is a pure
addition (point rows at retained blobs) with no migration of existing data.
Metadata (`name`, `document_type`, `description`, `case`, `client`) **is**
editable via `documents.services.update_document`.

### Permissions

- **`documents.view`** — all staff (they can already see every case; a case's
  documents follow, ADR-0008). Covers list, detail, **download**.
- **`documents.manage`** — office_manager, lawyer, paralegal, admin_clerk (the
  case handlers). Covers upload, metadata edit, retire.
- **finance_clerk = view-only** (can read/download for invoice/receipt context;
  cannot upload or retire).
- `sync_roles` maps `documents.{view,add,change}_document` (no `delete` codename —
  there is no hard-delete).

### Audit + case timeline

- `log_event` on **every** security-sensitive mutation:
  `DOCUMENT_UPLOADED` / `DOCUMENT_UPDATED` / `DOCUMENT_DOWNLOADED` /
  `DOCUMENT_RETIRED` (spec §46 lists "Document uploaded" + "Document downloaded"
  explicitly; architecture §"audit" pre-registered "document download (Phase 6)").
  `changes` carries **metadata only** — `name`, `content_type`, `size`, `sha256`,
  changed field names — **never file contents** (ADR-0009, architecture
  field-diff allowlist). django-auditlog registers `Document` with `file`
  **excluded** and the diff is metadata only.
- **Case timeline** — `CaseEventType.DOCUMENT_ADDED` / `DOCUMENT_REMOVED` (retire)
  when the document is case-linked, via `cases.services.record_case_event`
  (architecture §CaseEvent explicitly anticipated documents emitting events).
  **Downloads and metadata edits do not** emit a `CaseEvent` (downloads would
  flood the timeline; edits are minor) — only the audit trail records them.
  No other new `CaseEventType` members.

## Consequences

- The office never has a public document URL; a leaked pk yields a 404 for
  out-of-scope / retired rows and an audited stream otherwise.
- The curated validator is stricter (allowlist) but narrower than `libmagic`; if
  the office needs an unusual format, it is a one-line addition to the signature
  table + a Phase-12 review.
- Adding `DocumentVersion`, Contract/Invoice FKs (Phases 7/8), and a
  storage-retention GC (Phase 14) are all additive.
- `media/` stays git-ignored; `media/documents/` is created on first upload.
