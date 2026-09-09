━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      6 — Documents
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
            (same environment blocker as Phases 1–5; every other DoD item met)
Branch:     phase/6-documents — based on master @ c52c95a (Phase 5 merge, PR #4),
            NOT merged. One commit: phase(6): complete documents
Design:     docs/adr/0030-documents-storage-and-access.md (Accepted)

════════════════════════════════════════
1. WHAT WAS IMPLEMENTED  (spec §34–36, §46, §82 Phase 6)
════════════════════════════════════════

## `documents` app — one model

### Document (spec §34)
`name` (display name — **not** the filename) · `document_type`
(`DocumentCategory` `TextChoices`: pleading / contract / power_of_attorney /
judgment / evidence / correspondence / official / identity / financial / other —
stable legal vocabulary, a configurable table is a later change) · `description` ·
`file` (`FileField`, **private** storage) · `original_filename` (sanitised) ·
`content_type` (the **detected** type — the client's header is never read) ·
`size` (`PositiveBigIntegerField`) · `sha256` (hex — integrity + dup detection) ·
FK `case` / `client` (both **SET_NULL**, never CASCADE into a document, ADR-0022) ·
`uploaded_by` / `updated_by` (SET_NULL) · `TimeStampedModel`.
- **Retire (soft-delete)** via `deleted_at` + `deleted_by`, set only by
  `documents.services.retire_document`. Row + blob retained; list filters
  `.alive()`; a retired doc 404s everywhere except the admin.
  `default_permissions = ("add", "change", "view")` — **no delete**; admin
  `has_delete_permission = False`.
- The file is **immutable** once uploaded (spec §36 — versioning designed-for,
  not built). Metadata is editable.
- `DocumentQuerySet(ScopedQuerySet)` — `for_user` (all staff, a case's documents
  follow case visibility, ADR-0008), `alive`, `search`. 6 indexes.
- `download_filename` property — strips `/ \ " \r \n`, takes the basename,
  truncates 255, falls back to `document`.

## Private storage — never web-served (spec §35, docs/adr/0030)

- `documents.storage.PrivateFileSystemStorage(FileSystemStorage)` — **`.url()`
  raises** (`FileSystemStorage` falls back to `MEDIA_URL` when `base_url` is
  `None`; this override closes that).
- A dedicated `STORAGES["documents"]` entry (dev/prod →
  `PrivateFileSystemStorage(location=MEDIA_ROOT/"documents")`; tests →
  `InMemoryStorage`).
- `document_upload_path` → `<year>/<month>/<uuid4().hex><canonical-ext>` — the
  path is unpredictable and carries **no user-controlled segment** (no
  traversal); the extension is the validator's **canonical** one, never the
  client's `filename`.
- `config/urls.py` wires **no** MEDIA route; whitenoise serves only staticfiles.

## Upload validation — curated allowlist + magic bytes, no libmagic (spec §35)

`documents.validators.validate_upload(file)` (Arabic `ValidationError`, raises
on any failure, otherwise returns `ValidatedUpload(canonical_ext, content_type,
size, sha256)`):
1. **Size** ≤ `settings.DOCUMENTS_MAX_UPLOAD_MB` (default 25); rejects empty.
2. **Magic bytes** — the header is matched against a small curated signature
   table for exactly the allowed families: PDF, PNG, JPEG, GIF, TIFF, ZIP
   container (`PK\x03\x04` → docx/xlsx/pptx), OLE2 (legacy doc/xls/ppt), RTF, and
   a plain-text heuristic (no NUL in the first 8 KB + decodes) for `.txt/.csv/.md`.
   **Deny-by-default** — an unrecognised header is rejected.
3. **Extension must agree** — the client filename's extension must be in the
   detected family's set (both signals must agree).
4. sha256 is **streamed** in the same pass (`file.seek(0)` after).
- The client-supplied `Content-Type` header is **never** consulted.
- Hand-rolled (no `python-magic`/libmagic) → identical on the Windows editor host
  and Linux prod; a wider format set via `libmagic` is a documented Phase 12/14
  option that does not change the interface.

## `documents.services` — transactional, audited (metadata only)

`create_document` (validate → store → `full_clean` → save; `DOCUMENT_UPLOADED`
audit + `CaseEventType.DOCUMENT_ADDED` if case-linked) · `update_document`
(metadata only — `name/document_type/description/case/client`; freshly-fetched
diff + no-op guard, cf. bug-027; `DOCUMENT_UPDATED`) · `record_download`
(`DOCUMENT_DOWNLOADED` — audit-only, no `CaseEvent`) · `retire_document` (soft +
idempotent; `DOCUMENT_RETIRED` + `CaseEventType.DOCUMENT_REMOVED` if case-linked).
`_audit_meta` = `name / document_type / content_type / size / sha256` — **never
file bytes** (ADR-0009, architecture field-diff allowlist).

## `documents.selectors`

`document_list` (search + type filter + `?case`/`?client` + pagination,
`.alive()` by default, scoped), `case_documents`, `client_documents`.

## Views (spec §35 "secure download views")

`DocumentListView` / `DocumentDetailView` (`documents.view`) ·
`DocumentUploadView` / `DocumentUpdateView` (`documents.manage`; `?case`/`?client`
prefill verified against `for_user` querysets) · **`document_download`**
(`@require_GET` + `@require_capability(documents.view)` + `_get_document`
scope/`.alive()` → 404 · audited · `FileResponse(as_attachment=True,
filename=safe, content_type=detected)` + `X-Content-Type-Options: nosniff` ·
`FileNotFoundError` → 404, not audited) · `document_retire` (`@require_POST` +
`@require_capability(documents.manage)`).

## Permissions

- **`documents.view`** — all staff (a case's documents follow case visibility);
  **includes finance_clerk** (download for invoice/receipt context) but **not**
  `documents.manage`.
- **`documents.manage`** — office_manager, lawyer, paralegal, admin_clerk.
- `sync_roles` maps `documents.{view,add,change}_document` — **no `delete`
  codename** (there is no hard-delete).

## Audit + case timeline

- 4 `AuditAction`: `DOCUMENT_UPLOADED` / `DOCUMENT_UPDATED` /
  `DOCUMENT_DOWNLOADED` / `DOCUMENT_RETIRED` (spec §46 lists "Document uploaded" +
  "Document downloaded" explicitly; architecture pre-registered "document
  download (Phase 6)").
- 2 `CaseEventType`: `DOCUMENT_ADDED` / `DOCUMENT_REMOVED` — case-linked upload /
  retire only (downloads + metadata edits are audit-only; the architecture
  §CaseEvent explicitly anticipated documents emitting events). No other new
  `CaseEventType`.
- django-auditlog registers `Document` with `file` / `content_type` / `size` /
  `sha256` **excluded** from the automatic diff.

## Integration / other

- Case workspace: the disabled **المستندات** tab is now real (case documents +
  upload link with `?case=&client=` prefill, valid even for a closed case).
- Client profile: a **المستندات** card (recent 8 + upload/see-all links).
- Nav (spec §16): new **المستندات والعقود** group — **المستندات**
  (`documents:list`) active + **العقود** placeholder.
- `documents/0002_document_search_indexes` — trigram GIN (`name`, `description`,
  `original_filename`), PG-only, vendor-guarded; regression test keeps
  `TRGM_COLUMNS == SEARCH_FIELDS`.
- Settings: `STORAGES["documents"]`, `DOCUMENTS_MAX_UPLOAD_MB`,
  `FILE_UPLOAD_MAX_MEMORY_SIZE = 5 MB`, `FILE_UPLOAD_PERMISSIONS = 0o640`.
- `seed_demo_documents` (tiny valid PDFs, idempotent).

════════════════════════════════════════
2. FILES CHANGED
════════════════════════════════════════

New — `documents/` app:
  documents/  __init__.py  apps.py  models.py  storage.py  validators.py
              services.py  selectors.py  forms.py  views.py  urls.py  admin.py
              audit.py
  documents/migrations/  0001_initial.py  0002_document_search_indexes.py  __init__.py
  documents/management/commands/seed_demo_documents.py  (+ __init__ files)
  documents/tests/  factories.py  test_validators.py  test_models.py
                    test_services.py  test_views.py  test_permissions.py
                    test_smoke.py  __init__.py

New — templates:
  templates/documents/  _meta.html  document_list.html  document_detail.html
                        document_form.html

New — docs:
  docs/adr/0030-documents-storage-and-access.md
  docs/PHASE_6_REPORT.md

Modified:
  config/settings/base.py            STORAGES["documents"], DOCUMENTS_MAX_UPLOAD_MB,
                                     FILE_UPLOAD_* ; + "documents" in LOCAL_APPS
  config/settings/test.py            STORAGES["documents"] -> InMemoryStorage
  config/urls.py                     + path("documents/", …)   (no MEDIA route)
  core/permissions/capabilities.py   + DOCUMENTS_VIEW / DOCUMENTS_MANAGE, _DOCUMENT_HANDLERS
  accounts/management/commands/sync_roles.py  + _DOCUMENT_VIEW / _DOCUMENT_MANAGE
  core/navigation.py                 + المستندات والعقود group
  audit/models.py                    + 4 DOCUMENT_* AuditAction
  cases/models.py                    + 2 DOCUMENT_* CaseEventType
  cases/views.py                     المستندات tab (case_documents, can_documents*)
  templates/cases/case_detail.html   المستندات tab content
  clients/views.py                   client documents card context
  templates/clients/client_detail.html  documents card
  docs/architecture.md, docs/adr/README.md
  static/src/app.css + static/css/app.css  (rebuild only)

════════════════════════════════════════
3. DATABASE / MIGRATIONS
════════════════════════════════════════

- `documents/0001_initial` — `Document` table. 6 indexes (`-created_at`,
  `document_type`, `case`, `client`, `deleted_at`, `sha256`).
  `default_permissions = ("add","change","view")` — no `delete_document` codename.
- `documents/0002_document_search_indexes` — trigram GIN on
  `documents_document(name, description, original_filename)`. **PostgreSQL-only,
  vendor-guarded** (no-op on SQLite). Regression test:
  `test_search_field_set_and_trgm_in_sync`.
- `cases/0006_caseevent_document_types` — widen `CaseEvent.event_type` choices
  (metadata only; no column change).
- `makemigrations --check --dry-run` — **no changes detected**.

════════════════════════════════════════
4. TESTS & RESULTS
════════════════════════════════════════

**388 passed / 0 failed / 3 skipped** (SQLite). The 3 skipped are
`@pytest.mark.postgres`.

New `documents` tests (51):

- `test_validators` (9) — accepts PDF/PNG/DOCX + returns metadata; **rejects
  disallowed magic**, **extension/content mismatch**, **disguised executable as
  .pdf**, oversize, empty; plain text only for a text extension; **client
  Content-Type is ignored**.
- `test_models` (6) — `for_user` scoping; `.alive()` excludes retired; **no
  delete permission**; `download_filename` **sanitises path traversal** + falls
  back; trigram/SEARCH_FIELDS sync.
- `test_services` (7) — upload stores metadata + audits (**no file bytes in the
  audit `changes`**, stored path carries no client filename), `CaseEvent` on a
  case-linked upload, none without a case; rejects a bad file (no row created);
  **metadata edit leaves the file untouched**; no-op guard; **download is
  audit-only, never touches the case timeline**; **retire is soft + idempotent**,
  row kept, `DOCUMENT_REMOVED` + `DOCUMENT_RETIRED`.
- `test_views` (21) — login required (list, download); all-staff view, retired
  hidden; **pagination keeps scope on page 2**; search + type filter; **detail /
  download 404 for missing or retired**; upload requires `manage` (403 for
  finance_clerk, GET + POST); paralegal upload creates + audits + trims the name;
  **upload rejects a disguised executable (200 re-render, no row)**; **prefill
  ignores out-of-scope `?case`/`?client`**; **mass-assignment ignores
  sha256/size/uploaded_by/deleted_at**; **download streams `as_attachment` +
  `nosniff` + audits**; download is GET-only (405 on POST); **download 404 +
  no audit when the blob is missing**; **no public /media/ URL, storage `.url()`
  raises**; retire is POST-only + gated; retire soft-deletes; **edit form has no
  `file` field**; edit keeps an archived client in the picker; case المستندات tab
  + upload on a closed case.
- `test_permissions` (4) — capability matrix (finance_clerk view-only);
  finance_clerk can view + download but not upload/edit/retire;
  `sync_roles --check` clean.
- `test_smoke` (1) — 8 Phase-6 URLs render 200 + the download streams.

Existing suite: `cases` tests updated (المستندات is now a real tab).

Other gates: `ruff check` ✓ · `ruff format --check` ✓ · `pip-audit` — no known
vulnerabilities · `manage.py check` ✓ · `check --deploy --fail-level WARNING`
(prod settings, ephemeral key) — no issues (1 silenced) · seed chain
(`…_courts → _clients → _cases → seed_demo_documents`, idempotent) +
`sync_roles --check` clean.

════════════════════════════════════════
5. CODE-REVIEW FINDINGS & FIXES
════════════════════════════════════════

1. **`document_download` returned 500 (not 404) when the file blob was missing**
   on disk (an out-of-band change / future retention GC bug), and a phantom
   download would have been audited before the failure.
   → `document.file.open("rb")` is now wrapped: `FileNotFoundError` → `Http404`
   (reveals nothing), and `record_download` runs **after** a successful open, so
   a failed download is never audited. Regression:
   `test_download_404_when_blob_missing`.

No other Critical/High findings. Documented (not fixed — out of Phase 6 scope):
- **Orphaned blob on transaction rollback** — the storage write in
  `create_document` is not transactional; if a later statement in the atomic
  block fails, the DB rolls back but the blob remains. Very low probability
  (`log_event` / `record_case_event` rarely fail); a retention/GC sweep is a
  Phase 14 concern.
- **Pre-buffer upload cap** — `validate_upload` rejects >25 MB *after* Django has
  received the file; a hard request-body cap is the reverse proxy's job
  (`client_max_body_size`, Phase 14 deployment doc).

════════════════════════════════════════
6. SECURITY-REVIEW RESULT  —  PASS
════════════════════════════════════════

- **Object-level authz** — every view routes through `Document.objects.for_user()`
  `.alive()` + `assert_scoped` + `get_object_or_404` (or the scoped
  `document_list` selector). Retired / missing → 404. `?case`/`?client` prefill is
  verified against `Case/Client.objects.for_user`.
- **URL tampering → 404** — missing pk, retired row, and a missing blob all 404;
  no information leak, no 403-vs-404 oracle (all out-of-reach states are 404).
- **Capability checks explicit** — `CapabilityRequiredMixin` (CBVs) +
  `@require_capability` (function views); `documents.view` for read/download,
  `documents.manage` for upload/edit/retire. finance_clerk is view/download-only.
- **Never trust GET/POST ids** — all FK inputs go through `ModelChoiceField`
  (validated against a scoped queryset) or an explicit `.filter(pk=…).exists()`.
- **Mass-assignment** — upload form is a plain `Form` with explicit fields; the
  service computes `sha256 / size / content_type / original_filename /
  uploaded_by`; edit form `Meta.fields` has no `file`; the service filters to
  `METADATA_EDITABLE`. Tested.
- **CSRF** — every POST form carries `{% csrf_token %}`; `document_retire` is
  `@require_POST`; upload/edit are FormViews.
- **HTTP methods** — `document_download` `@require_GET` (405 on POST — a download
  is a read; the audit side-effect *is* the purpose), `document_retire`
  `@require_POST` (405 on GET).
- **Private files** — `PrivateFileSystemStorage.url()` raises; a separate storage
  entry; `upload_to` = uuid4 (unpredictable, no traversal); **no MEDIA route**
  (`/media/documents/<path>` → 404). Django public media serving is **not** used.
- **Downloads** — authenticated + capability + object-scoped + audited; stream
  via `FileResponse(as_attachment=True)` with the **detected** content type +
  `X-Content-Type-Options: nosniff` (and the global `SECURE_CONTENT_TYPE_NOSNIFF`)
  — even a PDF containing HTML/JS is downloaded, never rendered.
- **File validation** — extension **and** magic bytes must agree; deny-by-default;
  size limit; the client `Content-Type` is ignored; safe (uuid4) storage names;
  `original_filename` sanitised (path separators / newlines / quotes stripped);
  `download_filename` sanitised for the `Content-Disposition` header.
- **Audit** — 4 `DOCUMENT_*` actions cover upload / edit / **download** / retire;
  `changes` is metadata only (`name / type / content_type / size / sha256` or
  changed field names) — file contents never enter `AuditLog` or the auditlog
  diff.
- **No accidental hard delete** — no delete URL, admin delete disabled,
  `default_permissions` without `delete`, retire = soft (row + blob retained).
- **No new dependencies.**

════════════════════════════════════════
7. PERFORMANCE-REVIEW RESULT  —  PASS
════════════════════════════════════════

- `document_list` — `select_related("case", "client", "uploaded_by")` covers every
  template FK access; `.alive()` / filters hit the `deleted_at` / `document_type`
  indexes; pagination caps size; one query per submitted GET filter; trigram GIN
  (PG) for `search`.
- `document_download` — `_get_document` (1 query, `select_related`) + 1 audit
  INSERT; `FileResponse` streams in blocks (no full file in memory).
- `DocumentUploadView` — the file is read **once** (8 KB header + chunked
  sha256), bounded by 25 MB; the service reuses the form's `ValidatedUpload`
  (no second hash).
- Case detail — `+1` query (`case_documents`, lazy in the template). Client
  detail — `+1` query (`client_documents[:8]`).
- No N+1; no unnecessary filesystem work; `upload_to` is pure.
- `assertNumQueries` guards deferred to Phase 13 (consistent with Phases 2–5).

════════════════════════════════════════
8. PHASE 6 DoD VERIFICATION
════════════════════════════════════════

| DoD item (spec §82 Phase 6 + instructions)          | Status |
|-----------------------------------------------------|--------|
| Document model (name/type/file/description/links)    | ✅ |
| Secure private storage (no public URL)               | ✅ `PrivateFileSystemStorage`, no MEDIA route, uuid4 paths |
| Upload                                               | ✅ `DocumentUploadView` + `create_document` |
| Download (authorised, audited, secure view)          | ✅ `document_download` — auth + capability + scope + audit + attachment/nosniff |
| Authorization (object-level + capability + URL)      | ✅ `for_user` + `assert_scoped` + 404; `documents.view` / `documents.manage` |
| File validation (extension AND magic + size + safe)  | ✅ curated allowlist, deny-by-default, 25 MB, uuid4 names, sanitised filenames |
| Categories                                           | ✅ `DocumentCategory` + list filter |
| Case / client relationships                          | ✅ FK `case` + `client` (SET_NULL); case tab + client card |
| Audit integration                                    | ✅ 4 `DOCUMENT_*` actions (incl. download); metadata only |
| Security tests                                       | ✅ IDOR / anon / unauthorized / tampering / mass-assign / CSRF / methods / private-file / traversal / disguised-exe / download-auth |
| No mass assignment                                   | ✅ explicit fields + service allowlist |
| No hard-delete of legal records                      | ✅ retire = soft; no delete path |
| PostgreSQL-compatible schema + guarded PG-only bits  | ✅ + trigram migration vendor-guarded, regression-tested |
| Arabic-first, native RTL UI, Western digits          | ✅ logical utils, `{% translate %}`, `<bdi>`, `{% num %}` / `{% datestr %}` |
| Server-rendered, no new frontend framework           | ✅ |
| ruff / format / pip-audit / check --deploy / suite   | ✅ all clean, 388 pass |

════════════════════════════════════════
9. DEFERRED / UNVERIFIED CHECKS
════════════════════════════════════════

Environment blocker (identical to Phases 1–5 — this machine cannot run Docker or
PostgreSQL: low RAM, network stalls). Owner has accepted these each phase:

1. **Full suite not run against PostgreSQL 16** — SQLite only.
2. **`documents/migrations/0002_document_search_indexes` not executed** — PG-only,
   vendor-guarded → skipped on SQLite.
3. **`@pytest.mark.postgres` tests unverified** (3 skipped).
4. **`docker compose` full-stack smoke** — not run (equivalent verified via the
   Django test client, including the streamed download).
5. **`compilemessages`** — Docker-only (gettext); harmless (ships `ar`).
6. **Real-filesystem behaviour of `PrivateFileSystemStorage`** on Linux prod —
   tests use `InMemoryStorage`; `FILE_UPLOAD_PERMISSIONS = 0o640` and the
   `media/documents/` directory tree are unverified on a real FS.

Exact remaining PostgreSQL / Docker checks:
```
docker compose build
docker compose run --rm web python manage.py migrate   # cases 0006 + documents 0001/0002 apply
docker compose run --rm web pytest                      # expect 391 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d
curl -si localhost:8000/documents/                      # 302 -> /accounts/login/
# upload a real .pdf via the UI, then:
ls -l media/documents/$(date +%Y/%m)/                    # 0640, uuid4 name
curl -si localhost:8000/media/documents/<path>           # 404 (no route)
```

Deferred to later phases (scope, not gaps):
- Contract / Invoice document links — Phases 7 / 8 (additive FKs).
- `DocumentVersion` table / file replacement — future (spec §36; design is ready).
- `X-Accel-Redirect` / `sendfile` download offload — Phase 6+ if perf requires
  (grill D5); not needed at single-office scale.
- Document reports, global search over documents — Phase 10 / §47.
- Storage-retention GC for orphaned / retired blobs — Phase 14.
- `assertNumQueries` guards — Phase 13.

════════════════════════════════════════
10–13. GIT
════════════════════════════════════════

10. Commit hash:   1407070  ("phase(6): complete documents"; parent c52c95a = master @ Phase 5 merge; 48 files, +2564 / -17)
11. Push result:   pushed to origin/phase/6-documents (new branch, tracking set).
12. Current branch: phase/6-documents
13. Final git status: working tree clean; up to date with origin/phase/6-documents; 1 commit ahead of origin/master; NOT merged.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 6 COMPLETE — COMMITTED + PUSHED — WAITING FOR USER APPROVAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
