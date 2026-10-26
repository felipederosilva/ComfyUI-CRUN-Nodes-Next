# CRUN provider contracts and implementation boundaries

Research baseline: **25 October 2026**; comparative audit and 0.4 implementation:
**26 October 2026**. This is an unofficial integration. The 0.2 discovery checked
read-only authenticated balance, LLM inventory and Effects catalogs. The 0.3 audit
then compared CRUN with installed KIE 0.6.3 and identified missing native outputs,
reference adapters, complete recipes and conditional validation. One user-approved
Nano Banana Pro 1K image round trip subsequently completed, including native
IMAGE/MASK decoding, durable download and a confirmed 8-credit task charge.
Native-reference uploads and live video/audio generation remain unverified.

## Asynchronous APIs, native Comfy experience

[CRUN TaskInfo](https://docs.crun.ai/models/common/get-task-info) returns completed
media URLs for a task. KIE has a similar asynchronous task/result mechanism. A
JSON-only node output is not required by CRUN: 0.4 creative nodes wrap submission,
waiting, durable download and decoding, then expose native IMAGE/MASK, VIDEO or
AUDIO. The ordinary generator is a graph transformation feeding Preview/Save;
explicit API-task and legacy family contracts remain Advanced for compatibility.

The 26 October public-document audit retrieved five representative CRUN schemas
and their KIE counterparts. Their structural CRUN request schemas matched the
bundled definitions. That sample did not certify all catalog freshness, account
access or live behavior. Exact API fields still differ by provider: for example,
Kling Motion modes are CRUN `std/pro` versus KIE `720p/1080p`, and CRUN Seedance
I2V uses an ordered frame array rather than KIE's separate frame fields.

## Model reference and conditional adapters

Native simple image fields map to first/last frame, ordered reference batch,
mask and auxiliary image roles. Known simple video/audio URL fields now map to
motion/source video and ordered VIDEO/AUDIO references. Examples include
[CRUN Kling Motion Control](https://docs.crun.ai/models/kling/v3-motion-control)
and [Seedance 2.5 Reference to Video](https://docs.crun.ai/models/seedance/2-5/reference-to-video).
The selected CRUN schema determines which sockets apply; a reference operation's
capabilities must not be copied into its narrower I2V operation.

Imported schema checks are supplemented by explicit model guards:

- Kling 3 Omni R2V requires image/video references; video needs its role; image-only
  auto aspect is rejected; mixed image/video reference counts use CRUN's limits.
- Kling Motion Control requires one character image and one motion video.
- Implemented measured native-media checks enforce the verified Kling Omni and
  Kling 2.6 motion limits without borrowing KIE's unrelated numeric constraints.
- Wan 2.7 nested reference objects need image/video content, and reference-video
  requests observe the documented output-duration condition.

Sources: [Kling Omni schema](https://docs.crun.ai/models/kling/v3-omni-reference-to-video.json),
[Kling 2.6 motion](https://docs.crun.ai/models/kling/v2-6-motion-control), and
[documentation index](https://docs.crun.ai/llms.txt). These guards are a verified
subset, not proof that every prose-only restriction is encoded. Nested Wan,
complex face-swap and 3D structures still require specialized reference editors.
GIF-specific source contracts remain URL-based instead of being silently
transcoded to MP4.

## Upload contract

Native IMAGE/MASK references encode locally as PNG. VIDEO materializes as MP4;
AUDIO encodes to PCM16 WAV. Shape/value/size checks and applicable model guards
run before uploading. Numbered references preserve order and reject gaps.

The [documented upload flow](https://docs.crun.ai/common-api/file-upload) uses an
authenticated `GET /api/v1/client/files/upload-url` followed by a separate
credential-free PUT to storage with the matching content type. It is not a
multipart POST. Redirects and automatic retries are disabled. A content/credential
memory cache retains temporary receipts for 30 minutes; public documentation
lists temporary uploaded URLs, not permanent asset storage.

Prepare stays local. Estimate uploads required references and quotes without
creating a generation. Generate uploads, quotes, checks any positive optional
cap and available balance, then submits once for a new request/Take. An upload
can precede a later quote/cap/balance rejection. A zero optional cap disables that
local estimate check; existing positive limits remain intact.

## Effects contracts and output types

| Provider | Discovery | Generation input |
| --- | --- | --- |
| Kling | `GET /api/v1/client/job/kling-templates` | `model: kling/template`; `template_id`, `img_urls` |
| ByteDance | `GET /api/v1/client/job/bytedance-templates` | `model: bytedance/template`; `template_id`, `img_urls`, supported resolution |
| Vidu | `GET /api/v1/client/job/vidu-templates` | `model: vidu/template`; `template`, `images`, supported options |

All use the common CreateTask task mechanism with `x-api-key`. Kling's identifier
is `key`; ByteDance uses `TemplateId`, not preview `MediaId`. ByteDance `InputNum`
provides an explicit count, and `ConsumeItems` preserves resolution-specific
costs. Human instructions and repeated catalog appearances do not justify
inventing machine-verified image counts.

Sources:

- [Kling list](https://docs.crun.ai/templates/kling-template-list) and
  [generation](https://docs.crun.ai/templates/kling-template).
- [ByteDance list](https://docs.crun.ai/templates/bytedance-template-list) and
  [generation](https://docs.crun.ai/templates/bytedance-template).
- [Vidu list](https://docs.crun.ai/templates/vidu-template-list) and
  [generation](https://docs.crun.ai/templates/vidu-template).

The retained Effects discovery has 1,063 unique IDs from 1,088 source records.
Vidu's paginated discovery returned 521 rows representing 496 unique IDs.
Duplicates retain variants. Where output metadata establishes image or video,
the creative recipe uses that native kind. A Vidu definition without a known
output type remains an Advanced API example instead of promising VIDEO.

Catalog labels/instructions are untrusted text. Opt-in previews are not execution
authority and load directly from the remote host. No provider-owned preview bundle
or proprietary Effects engine is included. `build_effect_plan` remains an offline
draft helper, not a submission, quote or provider-accepted operation.

## AI Tools and media semantics

All 18 documented Tools retain schema-aware API entries. Known image/video output
contracts have typed creative nodes and preview/save recipes. Relevant sources:
[upscale](https://docs.crun.ai/ai-tools/image-upscale),
[expand](https://docs.crun.ai/ai-tools/image-expand),
[background removal](https://docs.crun.ai/ai-tools/image-background-remove), and
[video enhancement](https://docs.crun.ai/ai-tools/video-enhance).

IMAGE results expose MASK from alpha using Comfy's one-minus-alpha convention.
That preserves a useful transparency path but does not fabricate semantic masks,
layer separation, depth or geometry that an API does not return. Native AUDIO
result recovery decodes to waveform/sample-rate. 3D/LLM execution and unknown
output formats are not presented as complete native creative workflows.
Each Tool still needs representative authorized live validation for its actual
input/output format and billing. Likeness and watermark operations require the
user to have permission for the supplied media and intended changes.

## Completion, Takes and receipts

Creative jobs match a prepared request plus Take through a credential-keyed HMAC.
Raw prompts, reference URLs and API keys are not persisted in the job mapping.
Accepted IDs are stored before waiting; a cross-process submission lock coordinates
processes sharing configuration. Old creative mappings are not automatically
evicted, because they also prevent an old Take from creating another paid task.
Changing key/config/history does not retain a provider-wide exactly-once guarantee.

Increasing Take is an intentional new paid request. Explicit Resume existing task
bypasses old references and submission in Estimate/Generate; Prepare remains local.
Timeouts and ambiguous outcomes never automatically replace a task. A verified
local asset can be reused instead of downloading an expired media URL again.
Missing/corrupt cache entries retrieve the same ID, never regenerate.

The receipt separates estimate, provider-reported actual cost and timestamped
remaining balance. A cached local result may still trigger a read-only account
balance refresh. Balance deltas across concurrent jobs do not become confirmed
per-task costs. Missing values remain unavailable, not zero.

## Remaining evidence gates

The current implementation addresses the audit's default media pipeline and
reference/control defects. Local media, mocked transports and schemas cannot
prove upstream acceptance, entitled access, actual final charges or output quality.
[VALIDATION.md](../VALIDATION.md) records the full automated suite, actual Comfy
executor checks, the approved image round trip and remaining UI/live-model limits.
Additional representative live validation must review the
model, parameters, reference transmission and quote before a paid request.
