# Product direction

CRUN Next should give editors complete native-media workflows, with model-specific
controls and recoverable jobs. Discovery, implemented adapters, local acceptance
and live provider execution are separate readiness levels.

## Retained foundations — 0.1 to 0.3

- [x] Independent namespace, client, credentials and installation; KIE remains separate.
- [x] Native settings, Windows DPAPI, safe connection/balance checks and discovery.
- [x] Bundled 274 operation definitions, 64-ID LLM discovery union, 18 AI Tools and
  1,063 fixed Effects from the 25 October 2026 snapshot.
- [x] Schema-defined controls, 62 image/video families and optional credit caps.
- [x] Simple Prepare/Estimate/Generate actions with no extra permission checkboxes.
- [x] Single-attempt submission and existing-task Image/Video retrieval.

The 0.3 audit found metadata-only generator outputs, incomplete per-option
recipes, absent native VIDEO/AUDIO references and insufficient conditional model
validation. Prior passing tests did not establish a complete creative workflow.
These are the reasons for the 0.4 layer below.

## Implemented for 0.4.0

- [x] New creative nodes return native VIDEO, IMAGE/MASK or AUDIO directly after
  waiting for and saving the selected task result.
- [x] Old generated/family node IDs and output positions remain under Advanced
  API Tasks / Legacy Families; new Studio nodes provide the primary creative path.
- [x] Typed Model/Effect/Tool/Studio recipes include appropriate media sinks and
  source roles where their output contract is known. Unknown outputs and unsupported
  protocols remain clearly Advanced API examples.
- [x] Native simple VIDEO/AUDIO references, including Kling motion VIDEO and
  Seedance ordered video/audio references; PNG/MP4/WAV preparation/upload adapters.
- [x] Human field labels, compact ordinary text controls, profile-specific required
  roles, readable validation/status and distinct credit receipt states.
- [x] Explicit model guards for documented conditional reference rules, including
  Kling Omni roles/counts/auto aspect and relevant native metadata limits.
- [x] Same request/Take resumes its saved task; increase Take for an intentional
  alternative. Credential-keyed request digests omit raw prompts/reference URLs.
- [x] Accepted IDs recorded before waiting, cross-process submission coordination,
  no automatic creative-record eviction and no automatic replacement after an
  ambiguous submission, timeout or download failure.
- [x] Explicit Advanced resume ID bypasses old source requirements without upload
  or submission; Prepare remains local.
- [x] Durable completed media with verified local reuse, native AUDIO recovery
  and IMAGE transparency MASK output.
- [x] Estimated credits, provider-reported actual cost and timestamped remaining
  balance remain separate; no inferred task cost from balance deltas.
- [x] Full automated tests and actual Comfy executor acceptance for Prepare,
  completed Image/Save Image and synthetic VIDEO/AUDIO media sinks.
- [x] One approved Nano Banana Pro 1K provider round trip and 8-credit actual receipt.
- [ ] Live video/audio/reference-upload acceptance and final interactive canvas QA.

Implemented means a code path exists. It does not mean live account entitlement,
provider acceptance, output quality or every prose constraint was tested.
[VALIDATION.md](VALIDATION.md) records evidence and remaining verification limits.

## Current acceptance gate

1. Exercise Seedance I2V, Kling Motion Control and Nano Banana/Seedream editing as
   complete local Comfy graphs: named inputs, valid model controls, native result,
   playable/visible preview and saved output.
2. Verify model switching preserves references/caps, Prepare/Estimate block media
   appropriately, ordinary graph output targeting is correct, and missing inputs
   appear as readable feedback.
3. Test same-Take reuse after restart, explicit resume without old references,
   unknown submission outcome, concurrent-process submission and failed downloads.
   No replacement may be created automatically.
4. Verify transparent-image MASK and AUDIO channels/sample-rate behavior, durable
   local reuse, and independent final cost/balance receipts.
5. Review model, parameters, references and cost for a representative live request;
   run only the approved scope. Confirm actual task acceptance, media and billing.

## Next model-specific work

| Feature | Editor benefit | Acceptance evidence |
| --- | --- | --- |
| Nested reference editors | Character/motion/voice roles without raw JSON | Exact provider schema plus conditional media checks |
| Effects slot semantics | Know which subject or frame belongs where | Template-specific order/counts and correct result type |
| Storyboard and camera editors | Useful structured controls where actually supported | Verified model capability and parameter mapping |
| Task/asset board | Find, audition and resume previous work | Durable task-to-asset index and no paid regeneration |
| Characters/reference packs | Consistency across intentional jobs | Saved authorized references, clear roles and reuse |
| LLM protocols | Creative assistants and media planning | Verified chat/Messages/Responses contracts |
| 3D-native results | Use actual geometry/assets downstream | Verified result format and an appropriate asset adapter |
| GIF-specific tools | Preserve actual required formats | Format-aware reference/output adapters |

## Later gates

- Workflow-safe favorites and keyboard shortcuts.
- Visual Effects shelf improvements, opt-in previews and favorites.
- Opt-in batching with aggregate budgets and individual recoverable IDs.
- Provider cancellation only where documented; no refund promise.
- Remote/multi-user operation only after access-control and budget isolation design.
- Comfy Registry submission after packaging, security and representative execution
  checks; source metadata is not a listing or approval.

Do not infer camera controls, provider parity, output type or account access from
marketing titles. Keep exact wire contracts behind familiar creative controls.
Never automatically switch the billing provider or replace an uncertain paid task.
