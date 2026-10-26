# Security and scope

CRUN Next 0.3.2 targets a trusted, single-user, **loopback ComfyUI** installation.
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
Effects implementation is bundled. Remote generation references are public
HTTPS URLs; native files upload when Estimate or Generate is run. URL checks reject
embedded credentials and obvious local addresses but do not resolve DNS or
guarantee provider-side network isolation. Do not publish workflows containing
private media links or signed tokens.

## Native media uploads and retrieval

Connecting IMAGE/MASK media does not upload it. Prepare inspects/encodes locally
and produces local placeholders and reference metadata. Selecting Estimate and
running authorizes uploading connected references to obtain a quote; selecting
Generate and running authorizes the uploads and one paid task. This sends
the connected image/mask content to CRUN's documented upload endpoint. The image
is encoded as PNG with count, shape, finite-value, pixel and byte bounds checked
locally before upload. Exact model schemas still govern supported roles/counts.

Estimate does not authorize a paid task. Estimation with native media needs
temporary uploaded URLs, so an upload can occur before a quote/cap or balance
check prevents generation. Prepare never uploads. Model changes reset the action
to Prepare while retaining the optional credit cap. Legacy checkbox arguments
remain hidden for workflow compatibility; they are not additional action gates.

Upload receipts are cached only in memory for 30 minutes, scoped by credential
and content digest. CRUN documents a one-hour URL lifetime. No reusable upload URL
cache is written to the public package; a later Estimate/Generate after restart
may upload the references again. A workflow's user fields or outputs may contain private URLs
and must be reviewed before sharing. Temporary URLs are not durable asset storage.

Image/Video Result nodes poll only an existing task ID and cannot create jobs.
The selected result is downloaded over HTTPS with byte/time limits, redirect
following disabled and no CRUN account headers or environment credentials.
Obvious private addresses and resolved private destinations are rejected;
these checks are not a guarantee against every DNS/network attack. Downloads
persist under `output/CRUNResults`; treat private generated media as local data
that should not be committed or shared unintentionally. Image decoding is bounded.

Native VIDEO/AUDIO input upload and advanced nested media adapters remain
unimplemented. Use only media and likenesses you are authorized to process.

## Paid submission boundary

Generated starters default to Prepare. Prepare makes no provider request.
Estimate uploads required connected media and calls the quote endpoint without
creating a job. Only running a supported operation in Generate can reach
CreateTask after input, quote, optional-cap and balance checks.

`crun_max_credits` is an optional estimated-credit cap under Advanced. Zero
disables this cap; a positive existing cap remains in force and is not cleared
when changing models. The update does not remove or raise positive saved limits.

The gate validates documented inputs, obtains an estimate, checks any active
cap and the balance, and submits once. **A cap checks the estimate, not a provider-enforced final
spending cap.** Schema validation cannot cover every prose-only requirement.
No real provider upload, estimate, paid generation or generated-media download
has been tested for 0.3. LLM/dedicated protocols are prepare-only.

An output node set to Generate can submit again when Comfy executes it after
edits or queuing. Select Prepare before editing/sharing graphs. Journal markers and accepted IDs
omit keys, prompts and reference URLs. Unknown outcomes require inspecting CRUN
Logs and recovering the existing ID before intentionally submitting another job.
There is no automatic resubmission or paid-job replacement. Result retrieval may
poll and download the same accepted ID; timeout/interruption preserves that ID
for explicit retrieval retry. The journal is a recovery aid, not a provider
idempotency guarantee.

Credit receipt widgets display only returned metadata; they do not upload,
estimate or submit. They do not persist payloads, prompts, reference URLs or
credentials into their workflow state. The last quote is not a final charge and
the balance-at-check is not continuously live. A cap/balance rejection preserves
the quote for review without fabricating a task ID or a zero-cost success.

## Installation and reporting

The optional first-install helper copies an allowlist, verifies hashes and
refuses existing destinations. It does not start Comfy or modify KIE Next.
Packaging excludes local credentials, caches and journals. Keep backups outside
custom_nodes to avoid importing multiple copies.

Revoke a suspected leaked key in CRUN first. Report with a sanitized issue or
GitHub private vulnerability reporting if enabled. Never attach credential
files, raw headers, private URLs or unredacted Comfy configs. Provider errors
are sanitized; avoid publishing raw request/response dumps.
