# CRUN Effects and AI Tools research

Research date: **2026-10-25**. This is an unofficial integration. No CRUN
credentials, media uploads, task creation, or paid generation were used to
validate this skeleton. API documentation is evidence of an integration surface,
not proof of live availability or entitlement for a specific account.

## Effects: researched interfaces

| Provider | Discovery | Request shape |
| --- | --- | --- |
| Kling | `GET /api/v1/client/job/kling-templates` | `model: kling/template`; input has `template_id` and `img_urls` |
| ByteDance | `GET /api/v1/client/job/bytedance-templates` | `model: bytedance/template`; input has `template_id`, `img_urls`, and selected `resolution` |
| Vidu | `GET /api/v1/client/job/vidu-templates` | `model: vidu/template`; input uses `template`, `images`, and optional supported options such as `bgm` |

All three documented generation examples use the shared `CreateTask` endpoint
with `x-api-key`. This release **does not expose execution** of those requests.

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

The Vidu generation definition was readable, but the Vidu catalog page could not
be retrieved by the research browser. Its adapter is therefore defensive, not a
validated exhaustive catalog mapping. A live read-only catalog check is required
after the user adds their key. Unknown metadata stays unknown; it is not filled
with guessed values. The published docs' sample totals are not live counts.

Catalog names/instructions are untrusted text. Previews load only by explicit
user action; never interpret provider text as HTML. Preview URL checks reject
obvious private/credential-bearing addresses but are not a DNS security guarantee.
The `raw` metadata copy is for inspection, not automated instruction execution.

`build_effect_plan` is a pure local helper. Its output always says `draft`,
`execution_enabled: false`, and `ready_to_submit: false`. Payload fields follow the
provider-specific examples, while warnings identify missing references, unknown
slot counts and resolution validation still required. It must never be confused
with a completed task, cost quote, or provider-accepted request.

## AI Tools: researched, not executable yet

The [official documentation index](https://docs.crun.ai/llms.txt) lists dedicated
image and video utilities. The skeleton includes a **curated planned-feature
index**, not an authenticated live catalog or runnable tool implementation.

First candidates are image upscale/Pro, expansion, background removal, inpainting,
colorization, background regeneration, headshots and video enhancement. Relevant
definitions include [upscale](https://docs.crun.ai/ai-tools/image-upscale),
[expand](https://docs.crun.ai/ai-tools/image-expand),
[background removal](https://docs.crun.ai/ai-tools/image-background-remove), and
[video enhancement](https://docs.crun.ai/ai-tools/video-enhance). Each tool still
needs schema validation, native media adapters, result handling and an explicitly
authorized smoke test. Watermark removal is not prioritized; any future support
must respect ownership, licenses and attribution rights.

## Distinctive product direction

1. **Effects Library:** searchable template cards with explicit required-image
   slots, preview-on-demand, provider instructions and resolution-aware costs.
2. **Effect Plan:** prepare and inspect a request without spending credits; add
   preflight estimation and a deliberate execute gate in a later milestone.
3. **Finishing Toolkit:** purpose-specific visual controls for cutouts, masks,
   reframing and restoration instead of a wall of generic prompt nodes.
4. **Budget receipts:** distinguish estimate, reserved amount, final charge and
   current balance, rather than interpreting account balance differences as the
   exact cost of a job.
5. **Reusable recipes:** preserve template choice, ordered reference roles and
   finishing settings, without embedding API keys in saved workflows.

The first release provides the research and read-only foundation, not all five
finished experiences. It does not copy CRUN's branding, website media, or claim
official affiliation. Before distributing any provider-owned preview bundles or
templates, verify rights rather than assuming documentation implies permission.
