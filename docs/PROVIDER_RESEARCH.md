# CRUN Effects and AI Tools research

Research date: **2026-10-25**. This is an unofficial integration. The initial
0.1 research used public documentation. For 0.2, read-only authenticated balance,
LLM inventory and complete Effects catalogs were checked. Version 0.3 adds native
references, family dropdowns and existing-task result adapters. No real provider
upload, estimate, paid generation or generated-media download was performed for
0.3. Discovery and fake/local execution do not prove every operation works live
or is available to every account.

## Effects: researched interfaces

| Provider | Discovery | Request shape |
| --- | --- | --- |
| Kling | `GET /api/v1/client/job/kling-templates` | `model: kling/template`; input has `template_id` and `img_urls` |
| ByteDance | `GET /api/v1/client/job/bytedance-templates` | `model: bytedance/template`; input has `template_id`, `img_urls`, and selected `resolution` |
| Vidu | `GET /api/v1/client/job/vidu-templates` | `model: vidu/template`; input uses `template`, `images`, and optional supported options such as `bgm` |

All three documented generation examples use the shared `CreateTask` endpoint
with `x-api-key`. Version 0.3 preserves single-task submission with separate upload
and paid permissions. Known image fields can receive native Comfy connections;
result adapters poll an existing ID and return native IMAGE/VIDEO media. These
provider paths remain unverified with an actual paid round trip.

Sources:

- [Kling catalog](https://docs.crun.ai/templates/kling-template-list) and
  [generation definition](https://docs.crun.ai/templates/kling-template).
- [ByteDance catalog](https://docs.crun.ai/templates/bytedance-template-list) and
  [generation definition](https://docs.crun.ai/templates/bytedance-template).
- [Vidu generation definition](https://docs.crun.ai/templates/vidu-template) and
  [catalog documentation](https://docs.crun.ai/templates/vidu-template-list).

### Adapter boundaries

Kling's identifier is `key`; credits are `credit`. Its human-readable `info`
instructions must not be treated as a machine-verifiable input count. ByteDance
uses `TemplateId`, **not** the preview `MediaId`. `InputNum` is explicit input-count
metadata. `ConsumeItems` preserves resolution-specific costs rather than one
misleading universal price. English names fall back to the original title.

The initial browser could not retrieve the Vidu catalog page; authenticated,
paginated read-only discovery later returned 521 source rows representing 496
unique template IDs. Duplicate category appearances are retained in metadata and
map to the same fixed-template workflow. Unknown image counts remain unknown;
published sample totals and prose instructions are not machine-verifiable limits.

Catalog names/instructions are untrusted text. Previews load only by explicit
user action; never interpret provider text as HTML. Preview URL checks reject
obvious private/credential-bearing addresses but are not a DNS security guarantee.
The `raw` metadata copy is for inspection, not automated instruction execution.

`build_effect_plan` is a pure local helper. Its output always says `draft`,
`execution_enabled: false`, and `ready_to_submit: false`. Payload fields follow the
provider-specific examples, while warnings identify missing references, unknown
slot counts and resolution validation still required. It must never be confused
with a completed task, cost quote, or provider-accepted request.

## Model families and native media — 0.3

Creative tasks group models by family and compatible operation, such as Seedance
Image to Video, Text to Video and Reference to Video. Each node's version dropdown
retains the exact selected wire ID and schema. A union defines stable graph
connectors, while per-model profiles govern active controls, choices, numeric
bounds and image counts. Unsupported connected references are rejected, not dropped.

Recognized simple image fields map to named IMAGE/MASK roles: first/last frame,
reference batch, source image, mask or a known auxiliary image. Native batches
retain their order. Advanced HTTPS/JSON inputs remain available; nested face-swap
and 3D structures and native VIDEO/AUDIO upload need further adapters.

The [documented upload endpoint](https://docs.crun.ai/common-api/file-upload) accepts
multipart media and returns temporary URLs, documented as lasting one hour. Native
upload requires explicit permission, including before a quote uses connected
images. A memory-only 30-minute cache is scoped to credential and content. Prepare
does not send media. Upload permission never authorizes paid task submission.

Result adapters inspect the same task through the [task contract](https://docs.crun.ai/models/common/get-task-info),
poll within a bounded timeout, download one selected result without credential
headers, retain a local copy in output/CRUNResults and expose IMAGE/VIDEO for Comfy
preview/save. They cannot create a replacement job after a timeout.

## AI Tools: current progress

The [official documentation index](https://docs.crun.ai/llms.txt) lists dedicated
image and video utilities. The 0.1 skeleton included a curated planned-feature
index. All 18 documented tool operations now have schema-aware Nodes-menu entries
and workflow starters. Recognized image/mask roles accept native references.
Their workspace cards inspect inputs; supported media-task nodes submit only
through explicit upload/generation permissions.

First candidates are image upscale/Pro, expansion, background removal, inpainting,
colorization, background regeneration, headshots and video enhancement. Relevant
definitions include [upscale](https://docs.crun.ai/ai-tools/image-upscale),
[expand](https://docs.crun.ai/ai-tools/image-expand),
[background removal](https://docs.crun.ai/ai-tools/image-background-remove), and
[video enhancement](https://docs.crun.ai/ai-tools/video-enhance). Each tool still
needs representative authorized live validation; implemented schema/media/result
adapters are not evidence that every tool works end to end. Likeness and watermark
operations require authorization for the source material and intended changes.

## Distinctive product direction

1. **Effects Library:** searchable template cards with explicit required-image
   slots, preview-on-demand, provider instructions and resolution-aware costs.
2. **Effect Plan:** prepare and inspect a request without spending credits;
   individual nodes now provide preflight estimation and a deliberate execute gate.
3. **Finishing Toolkit:** purpose-specific visual controls for cutouts, masks,
   reframing and restoration instead of a wall of generic prompt nodes.
4. **Budget receipts:** distinguish estimate, reserved amount, final charge and
   current balance, rather than interpreting account balance differences as the
   exact cost of a job.
5. **Reusable recipes:** preserve template choice, ordered reference roles and
   finishing settings, without embedding API keys in saved workflows.

The current release adds practical workflow adapters to the research and discovery
foundation; the proposed experiences still need real editorial validation. It
does not copy CRUN's branding, website media, or claim
official affiliation. Before distributing any provider-owned preview bundles or
templates, verify rights rather than assuming documentation implies permission.
