# Security and execution scope — 0.4.0

CRUN Next targets a trusted, single-user **loopback ComfyUI** installation. It is
not a hardened public or multi-user service. A remote/shared deployment needs a
separate authentication, authorization and spending design.

## Credentials and local data

The local bridge checks loopback peer/Host addresses, same-origin requests and a
process-local nonce for actions. Key entry uses a password control and sends the
key to the local backend. Status routes do not return it; workflows, browser
localStorage and persisted Comfy settings do not store it.

Windows keys use current-user DPAPI, with no plaintext fallback. Other platforms
use restrictive owner permissions, not encryption. `CRUN_API_KEY` overrides saved
storage; removing the saved key does not unset that environment variable. Another
custom node or compromised same-user process can still access keys and submit
requests. DPAPI protects at rest, not against a compromised running user session.

Configuration, safe connection receipts, catalog caches, task journals, creative
job mappings and completed-asset indexes are separate files outside the package.
Do not commit or publish that directory. Generated media and diagnostic outputs
may contain private material even though journals omit prompts and reference URLs.

## Requests, discovery and previews

Credentialed calls use fixed HTTPS CRUN endpoints without redirects or automatic
retries. Documentation refresh uses official docs hosts without a key and bounded
sizes/concurrency. Authenticated inventory/Effects discovery uses read-only GETs.
Node registration, opening a workflow and selecting a model do not submit tasks.
Catalog presence is neither authorization nor proof of entitlement or execution.

Catalog strings are untrusted metadata and render as text. Optional remote
previews load only on user action and reveal the browser IP to the media host.
No provider preview bundle or proprietary Effects implementation is included.
Native media and advanced URL fields are alternative sources, not hidden upload
permissions. Review private URLs and signed links before sharing a workflow.

## Native reference boundary

Prepare validates and materializes IMAGE/MASK/VIDEO/AUDIO locally. Connecting a
port or changing a model does not upload media. Estimate uploads required
references to quote a task. Generate uploads required references before its
quote/cap/balance checks and one new submission. Therefore an upload can precede
a later rejection for insufficient balance or an optional cap.

Recognized image fields encode to bounded PNG; masks retain their documented
white-as-affected input semantics. Native VIDEO materializes locally as MP4 and
AUDIO as PCM16 WAV. Generic size/shape/value checks and the implemented
model-specific reference guards run before upload. Numbered references preserve
order and reject gaps. These checks do not establish every prose-only provider
limit, support nested reference structures, or convert a GIF-specific contract
into an MP4 contract.

Uploads use a fixed authenticated `GET /api/v1/client/files/upload-url` followed
by a separate **credential-free PUT** to the returned storage URL. That storage
session does not attach CRUN headers or environment/netrc credentials and follows
no redirects or automatic retries. MIME/extension/signature and bounded-byte
checks cover PNG, MP4 and WAV. URL validation rejects embedded credentials and
obvious local destinations; upload-destination checks are not a complete DNS or
provider-side network isolation guarantee.

Upload receipts are cached in memory for 30 minutes, scoped to content, media
type and configured credential. CRUN upload URLs are temporary. The cache is not
durable storage and is not written into the public package. A new session may
upload again when the user intentionally runs Estimate/Generate.

## Generation intent and optional credit cap

Creative recipes default to Prepare. Estimate creates no generation task.
Generate validates, obtains a quote, enforces any positive `crun_max_credits` and
checks balance before a new submission. Zero disables that optional cap;
positive saved limits are retained across model changes. No extra upload/paid
checkbox is required by the simple action flow. The cap checks an **estimate**,
not a provider-enforced ceiling on the final charge.

Ordinary creative generators are graph transformations with native media outputs
and `OUTPUT_NODE=False`. They run through the selected connected output graph.
Legacy API-task nodes retain their IDs, output slots and prior output-node
behavior under Advanced; a legacy node left in Generate can execute again when
Comfy queues uncached work. Those legacy contracts do not gain Take-based reuse
merely by upgrading the package.

## Creative Take records and unknown outcomes

New creative nodes identify a prepared request plus Take through an HMAC keyed
by the configured API credential. This permits local matching without persisting
the raw request, prompt, reference URL or API key. It is credential-scoped, not a
provider-wide account identity: changing key/configuration or removing history
must not be treated as retaining automatic deduplication.

A local cross-process submission lock coordinates processes sharing the config
directory. Before CreateTask, a submitting marker is written; an accepted task ID
is recorded before waiting/downloading. Repeating the same recorded request/Take
retrieves that task. Changing model, settings, references or Take can define a
new paid request. **Increase Take intentionally**, and clear an explicit resume
ID when intending a new generation.

Creative mappings are not automatically evicted: they also serve as paid-request
tombstones. Unreadable/full history blocks generation instead of silently
resetting mappings. Preserve history/task IDs before manual maintenance. These
controls mitigate repeats but are not a provider-enforced exactly-once protocol.
Do not restore an empty/stale history and assume old Takes remain protected.

An unknown submission outcome never triggers an automatic replacement. Inspect
CRUN Logs, identify the accepted task if present, then use **Resume existing
task** under Advanced. In Estimate/Generate, resume bypasses old source media,
quote and submission; Prepare remains offline. Timeouts, failed downloads and
local cancellation keep the task ID; they do not promise remote cancellation,
refund or a free retry.

## Completion, local reuse and credits

Completion polls only the existing ID, bounds waits/downloads, omits provider
credentials from media GETs and follows no redirects. Resolved private download
destinations are rejected; DNS/network checks are a mitigation, not a complete
network security boundary. Persisted media under `output/CRUNResults` is private
local data and should not be committed or shared accidentally.

Completed-asset lookup is credential-scoped and validates local filename,
location, byte count and content digest before reuse. A missing/corrupt/evicted
cache entry can query/download the **same task** again; it never creates a new
one. The bounded asset index is separate from the non-evicting creative job
history. Stored indexes omit signed media URLs. A local-only reuse can return an
empty URL while its native media output remains usable.

Image decoding bounds pixels and exposes the Comfy transparency mask as one
minus alpha. AUDIO decoding bounds output samples/memory. VIDEO requires a
current Comfy runtime. Do not interpret these adapters as evidence that every
upstream model returns a compatible file or every requested role works live.

Receipts distinguish the estimated quote, provider-reported actual task cost and
a separate timestamped account-balance check. Unknown values remain unavailable;
shared balance deltas do not become a per-task cost. A local completed asset may
be reused without a download while the creative node refreshes account balance
read-only.

## Packaging and verification

The runtime package uses an explicit allowlist, archive CRC and SHA256 checks.
Credentials, journals, private asset indexes, user outputs, temporary URLs and Git
history are excluded. Installation backups must stay outside `custom_nodes`.
KIE Next remains a separate installation and provider configuration.

One expressly approved Nano Banana Pro 1K round trip completed for a confirmed
8-credit task charge. It required no user-media upload. Native image decoding,
local reuse and actual Comfy Save Image passed. Synthetic VIDEO/AUDIO executor
checks are separate from live video/audio generation. Interactive browser checks
were stopped by the Computer Use safety tool; [VALIDATION.md](VALIDATION.md)
records this limit and the final automated evidence. Unsupported
LLM/3D protocols and unknown Effect output types remain Advanced rather than
claiming complete typed execution. Comfy Registry publication is not implied.
