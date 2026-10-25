# Product direction

CRUN Next should become an Effects and AI Tools workbench, not just a renamed
copy of KIE Next. This roadmap is a proposal, not a feature-completion claim.

## Foundation — 0.1

- [x] Separate namespace, local key storage, explicit connection check.
- [x] Live balance, non-generating estimates and existing-task inspection.
- [x] On-demand Kling/ByteDance/Vidu effect-catalog adapters.
- [x] Draft payload preparation, disabled paid execution.
- [x] AI Tools research cards with official sources and planned labels.
- [ ] Account-backed catalog/estimate checks using a user-provided key.

## Next gate — one useful effect, one useful tool

1. Enable **one** verified effect with native image references and preflight checks.
2. Add **one** practical tool, such as masked image inpainting, with typed native
   IMAGE/MASK sockets, supported limits and a before/after result.
3. Before sending: name the provider/model, list files being uploaded, quote the
   estimate with its provisional status, and require explicit generation intent.
4. Submit once, retain task ID, poll that task and recover it after a restart.
   A timeout must never silently create a replacement paid task.
5. Save results durably and record actual cost; do not treat temporary CDN URLs
   as permanent assets or infer per-task cost from a changing shared balance.

## Differentiators to validate

| Idea | Editor benefit | Initial validation |
| --- | --- | --- |
| Named reference slots | Know which character/product/image goes where | A verified two-image template with clear labels |
| Effects Shelf | Find and compare effects visually | Search, categories, opt-in previews, favorites |
| Repair recipes | Chain remove background → inpaint → upscale | Native media pipeline and original/result comparison |
| Budget guard | Reduce accidental spend | Authoritative estimate, ceiling, no automatic resubmission |
| Audition board | Compare intentional alternative takes | Persistent result IDs, costs and original references |
| Output adapters | Make results usable by downstream Comfy nodes | Real IMAGE/VIDEO/AUDIO round trips |

## Later

Model-specific forms generated from verified CRUN schemas; progressive task
history and cancellation where supported; 3D result adapters; opt-in batching
with explicit aggregate budget; workflow recipes that remain provider-specific.

Do not promise arbitrary camera controls, cross-provider parity, native feature
availability or all-model coverage without checking the relevant API contract.
Do not automatically switch billing providers. Public Registry publication needs
its own security/quality review after the alpha is authenticated and exercised.
