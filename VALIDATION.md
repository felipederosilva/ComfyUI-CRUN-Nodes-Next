# 0.1.0 alpha validation

Checked on Windows, 2026-10-25.

## Verified

- 63 offline Python tests: 62 passed, one Unix-only permission test skipped.
- 7 offline JavaScript DOM/helper tests passed.
- Fake-key Windows DPAPI round trip; plaintext absent from persisted ciphertext.
- Local HTTP boundary tests: nonce, cross-origin, remote peer/Host, oversized JSON,
  generic errors and credential-free status responses.
- Mocked provider contracts: balance, task inspection, provider-specific catalogs
  and non-generating credit estimates; no paid task submission interface exists.
- Model/task absence is not represented as a successful zero-cost response.

## Actual ComfyUI checks

- Started ComfyUI 0.42.5 / frontend 1.55.18 in an isolated CPU-only profile.
- Seven CRUN nodes registered successfully; no KIE package loaded or modified.
- Browser checked: launcher, Connection panel, Settings category/action, Effects
  provider selector, and nine planned AI Tools cards. No provider request needed.
- Source ZIP CRC verified; runtime package is built from an explicit allowlist.
- First-install helper tested against a temporary Comfy fixture; rejects an
  existing destination and a directory that is not a backend Comfy installation.

## Publication and installation

- First-installed 23 allowlisted files into the actual Comfy Desktop custom_nodes
  directory under a new ComfyUI-CRUN-Nodes-Next folder; no KIE files changed.
- GitHub offline CI passed on Ubuntu and Windows for initial code commit 54b5b16:
  https://github.com/felipederosilva/ComfyUI-CRUN-Nodes-Next/actions/runs/40228027516
- Runtime ZIP also includes the two original workspace screenshots; no API key,
  config file, cache, existing user data or Git history is distributed.

## Not checked / deliberately not implemented

- Real CRUN account authentication, balances, estimates, entitlement and current
  Effects catalog response shapes (especially Vidu).
- CRUN generation/upload/media round trip; none exists in this alpha.
- AI Tools execution and full-model node coverage.
- Multi-user, LAN or publicly exposed Comfy servers; this alpha is loopback-only.
- Other operating systems in an interactive Comfy installation.

Fake responses and a fake credential are test fixtures, never evidence of live
CRUN success. No authenticated CRUN call, upload or paid generation was made
while preparing this skeleton.
