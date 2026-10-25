# Security and scope

CRUN Next 0.2 targets a trusted, single-user, **loopback ComfyUI** installation.
It is not a hardened multi-user service. Do not expose the server publicly
without a separate access-control design.

## Credential boundary

The local bridge checks peer/Host loopback addresses, same-origin requests and a
process-local nonce for actions. Keys enter a password control and are sent to
the local backend. They are not returned by status routes or saved as graph
widgets, workflow fields, browser localStorage or persistent Comfy setting values.

Windows storage uses DPAPI for the current user with no plaintext fallback.
Other platforms use restrictive owner permissions but **not encryption**.
`CRUN_API_KEY` overrides saved storage; deleting a saved key does not unset it.
Credential, nonsecret connection receipt, catalog cache and task journal are
separate files outside the extension. Status receipts are historical and bound
to a key fingerprint. Do not place configuration in Git or share it.

DPAPI protects data at rest, not against same-user malware or compromised custom
nodes/backends. These can still access secrets or submit requests. Use a dedicated
CRUN key and provider-side usage limits where available.

## Requests, catalogs and previews

Credentialed requests use fixed HTTPS CRUN endpoints without redirects or
automatic retries. Public documentation fetches use fixed official docs hosts
without a key, with bounded downloads/concurrency. Authenticated discovery uses
read-only GETs. Catalog loading and node registration are local-only; opening a
workflow does not submit a job.

Catalog labels/schemas are untrusted metadata. Labels render as text, not
executable HTML. Catalog presence is neither authorization nor proof of access
or tested execution. Exact model IDs come from schemas/documented discovery.

Optional HTTPS previews load on user action, without a backend proxy, and expose
the browser's IP to the media host. No external preview files or proprietary
Effects implementation is bundled. Current generation references are public
HTTPS URLs; native files are not uploaded automatically. URL checks reject
embedded credentials and obvious local addresses but do not resolve DNS or
guarantee provider-side network isolation. Do not publish workflows containing
private media links or signed tokens.

## Paid submission boundary

Generated starters default to `prepare`, paid permission disabled and budget zero.
Prepare makes no provider request. Estimate calls the non-generating quote
endpoint. Only a supported media operation in `generate`, with explicit
permission and a positive ceiling, can reach CreateTask.

The gate validates documented inputs, obtains an estimate, checks ceiling/balance
and submits once. **The ceiling checks the estimate, not a provider-enforced final
spending cap.** Schema validation cannot cover every prose-only requirement.
No real paid generation has been tested in this release. LLM/dedicated protocols
are prepare-only.

An armed output node can submit again when Comfy executes it after edits or
queuing. Disarm before editing/sharing graphs. Journal markers and accepted IDs
omit keys, prompts and reference URLs. Unknown outcomes require inspecting CRUN
Logs and recovering the existing ID before intentionally submitting another job.
There is no automatic resubmission, polling, download or result replacement.
The journal is a recovery aid, not a provider idempotency guarantee.

## Installation and reporting

The optional first-install helper copies an allowlist, verifies hashes and
refuses existing destinations. It does not start Comfy or modify KIE Next.
Packaging excludes local credentials, caches and journals. Keep backups outside
custom_nodes to avoid importing multiple copies.

Revoke a suspected leaked key in CRUN first. Report with a sanitized issue or
GitHub private vulnerability reporting if enabled. Never attach credential
files, raw headers, private URLs or unredacted Comfy configs. Provider errors
are sanitized; avoid publishing raw request/response dumps.
