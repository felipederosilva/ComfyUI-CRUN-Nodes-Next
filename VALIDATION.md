# 0.2.0 catalog alpha validation

Checked on Windows, 2026-10-25.

## Verified

- 123 offline Python tests: 122 passed, one Unix-only permission test skipped.
- 11 JavaScript tests and frontend syntax check passed.
- Every one of 1,337 generated node classes executed its default preparation
  locally while provider network requests were blocked: no network calls.
- 1,337 flat Comfy workflow templates map to every bundled catalog entry and
  unique Effect; all start with prepare / paid permission false / credit ceiling 0.
- Manifest maps all 1,088 Effects source records to 1,063 unique template recipes.
  Repeated Vidu categories are preserved as metadata, not invented execution variants.
- Model-specific required fields, enum choices, JSON arrays/objects, numeric bounds,
  URL checks and text patterns; unsupported protocols remain preparation-only.
- Windows DPAPI fake-key round trip and fresh settings-module load preserve the
  credential; safe connection/balance receipts persist separately. A changed key
  invalidates the old receipt. No plaintext key is stored in frontend settings.
- Local HTTP nonce, same-origin/loopback boundary, bounded JSON, sanitized errors
  and credential-free status responses.
- Mocked paid-submission gate requires permission and positive budget, checks
  estimate and balance, preserves task IDs and never retries. Ambiguous transport
  and 5xx responses instruct recovery from CRUN Logs. Invalid journals block submission.

## Actual ComfyUI checks

- Isolated CPU-only ComfyUI 0.42.5 / frontend 1.55.18 starts successfully.
- Comfy's object-info API registers 1,344 CRUN nodes: 1,337 catalog nodes plus
  seven setup utilities. Workflow-template index exposes all 1,337 JSON recipes.
- A video model, a fixed Effect and an AI Tool completed preparation through
  Comfy's actual execution queue without provider calls or paid generation.
- Browser checked: native Settings > CRUN Next custom rows, save with an isolated
  fake key, empty password field after save, masked saved state after reopening
  Settings, launcher, model-library counts, filtering and schema inspection.
- The unsaved test graph was preserved; browser reload was not used as a storage
  test. Fresh-module tests verify persistence independently of the open page.

## Read-only live CRUN checks

- Existing saved key accepted by the documented balance endpoint.
- Authenticated LLM inventory returned 55 IDs. The union with documentation is
  64 LLM definitions; nine documentation-only IDs remain explicitly labeled.
- Public schema discovery plus the live LLM inventory yields 274 catalog entries,
  273 wire model IDs, 21 providers and zero unresolved definitions in this snapshot.
- Complete paginated Effects discovery: Kling 226, ByteDance 341, Vidu 496 unique
  template IDs (521 Vidu source rows). No key, balance or account identifiers are
  bundled in catalog or workflow metadata.

## Not checked / not implemented

- No actual paid generation, cost estimate, upload or provider-media round trip
  was performed. Mocked submission success is not live generation evidence.
- Native IMAGE / MASK / VIDEO / AUDIO uploads, decoded media outputs, automatic
  task polling, result downloads and cancellation are not implemented.
- LLM and non-CreateTask dedicated protocols are preparation-only.
- Complex prose-only conditions and template reference meanings still require
  review of each provider's instructions; catalog presence is not entitlement.
- Interactive Comfy on other operating systems, shared/LAN/public servers and
  Comfy Registry publication have not been validated for this release.

## Local installation

- Updated 1,366 allowlisted files in the actual Comfy Desktop CRUN extension.
- Overwritten files were backed up outside custom_nodes. Credential-file hash
  and every existing KIE extension file were verified unchanged.
- Fresh installed-package import confirms version 0.2.0, 1,344 registered nodes,
  saved key present and historical connected status. Sora entries register as Video.

The runtime ZIP uses an explicit file allowlist and CRC/SHA256 verification.
Credentials, user caches, task journals and Git history are excluded. Publication
receipts are reported separately after those operations complete.
