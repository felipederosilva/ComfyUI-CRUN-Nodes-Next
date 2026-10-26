# 0.4.0 native-media creative workflow validation

Verified **26 October 2026**, Windows. This document separates implementation,
automated/local Comfy executor evidence, retained 0.3 history and the one approved
live provider test. Interactive canvas verification remains Not Checked.

## Current 0.4 code under verification

- New creative generator contracts return VIDEO directly, IMAGE plus transparency
  MASK, or AUDIO; URL, task ID, estimated/actual cost, remaining balance and
  diagnostic JSON are separate outputs.
- Creative nodes use `OUTPUT_NODE=False` and connect to the appropriate native
  media sink. Typed recipes include source roles and preview/save; unknown-output,
  3D and unsupported LLM operations remain Advanced API examples.
- Legacy generated and family IDs/output positions remain stable under Advanced
  API Tasks / Legacy Families. They retain their old API-task execution behavior.
- Native simple VIDEO/AUDIO URL fields have named/ordered reference sockets.
  PNG/MP4/WAV materialization stays local in Prepare; Estimate/Generate upload as
  required. URL/native conflicts, numbered-reference gaps and known model
  conditions fail before upload.
- Dedicated conditional guards supplement machine schemas for Kling Omni,
  motion-control and Wan 2.7 reference requirements. They do not cover every
  documented model/prose restriction.
- Prepare/Estimate return blocked media until there is an actual result.
  Preparation problems have readable validation feedback; quotes are not final
  charges and unknown balance/cost are not zero.
- Same prepared request/Take reuses its recorded task across restart. New creative
  mappings use a credential-keyed HMAC and retain accepted IDs without persisting
  prompts/reference URLs. Cross-process submission coordination and no automatic
  job-mapping eviction protect the local reuse path.
- Explicit Advanced resume ID retrieves the existing task without old references,
  quote or submission in Estimate/Generate. Prepare remains local. Unknown
  submission outcomes/timeouts never trigger replacement generation.
- Completed media uses bounded download/decoding and a content-verified local
  index. The asset index is bounded separately from the non-evicting creative
  submission records. Cached local media can avoid a download; creative completion
  may still refresh account balance read-only.

## Current local evidence

- Native reference suites passed locally during implementation: 11 media, 13
  native-node, 26 client, 15 execution and 10 generated-definition tests. These are
  component checks, not the final release-wide count.
- Transport tests mock provider calls and verify PNG/MP4/WAV MIME/extension,
  presigned-ticket GET and credential-free PUT, no redirects/retries, content/key
  cache scope, and no paid submission during estimation.
- Real local Comfy VideoFromFile materialization passed using an independently
  created synthetic AVC MP4: 64 x 48, 12 frames, 24 fps, 0.5 seconds. Native AUDIO
  preparation passed for a one-second 16 kHz mono PCM16 WAV. No provider request
  occurred. Evidence was saved outside the package in
  `outputs/crun-v04-native-qa/native-adapter-proof.json`.
- Model guard tests exercised documented conditional reference errors using
  synthetic values and no provider calls. Final combined counts follow below.

## Final 0.4 release evidence

| Check | Status | Evidence |
| --- | --- | --- |
| Full Python suite | Pass | 250 checks: 249 passed, one Unix-only permission skip on Windows; Comfy Python 3.13 |
| Full JavaScript suite | Pass | 41 frontend checks: profiles, labels, receipts, Advanced/Take and preserved caps |
| All generated recipes | Pass | 1,399 recipes: 1,314 typed native chains, 85 clearly marked Advanced examples; links and widget serialization verified |
| Legacy graph contracts | Pass | All 1,399 old generated/family definitions retain widget order; original IDs and output positions remain |
| Native generator contracts | Pass | Native media first; IMAGE adds MASK; ordinary creative nodes are not independent output targets |
| Real Comfy Prepare | Pass | Missing Seedance image produced readable validation; Save Video blocked; task journals unchanged |
| Live provider image | Pass, one model | Approved Nano Banana Pro 1K square prompt-only task: actual 8 credits, IMAGE[1,1024,1024,3], MASK[1,1024,1024] |
| Real Comfy Save Image | Pass | Existing approved task resumed through native creative node to SaveImage; output descriptor and saved PNG verified |
| Completed local reuse | Pass | Reopened the actual approved image with provider polling/download forbidden; no provider request |
| Native VIDEO to SaveVideo | Pass, synthetic | Actual Comfy executor; saved/decoded AVC MP4, 64x48, 12 frames, 24fps, 0.5s; no provider access |
| Native AUDIO to PreviewAudio | Pass, synthetic | Actual Comfy executor; saved/decoded FLAC, 16kHz, 8,000 samples; no provider access |
| Recovery/concurrency | Pass, offline | Same Take, unknown submission, failed retrieval, separate credentials, cross-process lock, non-evicting mappings and explicit resume checks |
| RGBA/MASK/AUDIO adapters | Pass, local | Actual alpha inversion and PCM decoding/size/sample checks |
| Interactive browser/canvas | Not checked | Windows Computer Use stopped because it could not reliably determine the active browser URL; no further UI input was issued |
| Runtime ZIP/install integrity | Release gate | Explicit allowlist, CRC/SHA256, saved-key scan and installed-file/KIE/credential checks run before publication |
| GitHub CI | Release gate | Windows/Ubuntu workflow results on the release commit are authoritative; prior-release success is not used |
| Live native uploads, video/audio generation, every model | Not checked | No authorization to expand the one approved image task |

The real image test is provider execution evidence for that model/settings only.
Synthetic video/audio prove native media integration and saving, not upstream
video/audio model acceptance. Financial receipts are private; the public package
contains no account balance, key, task ID, user-media reference or private journal.

## Retained history — 0.3 and 0.3.2 only

The prior release completed 187 Python checks (186 passes, one Windows skip) and
34 JavaScript tests, plus Windows/Ubuntu CI. Its isolated Comfy 0.42.5 / frontend
1.55.18 checks covered local Prepare execution, family model switching, native
IMAGE links and a synthetic credit-receipt emitter. Those are historical checks;
they do not validate the new 0.4 combined creative path or a live provider round trip.

The 0.3 architecture returned JSON/task ID/credits on generators; only its 62
Studio recipes supplied separate retrieval/sink chains. The 1,337 per-option
recipes omitted that chain. The 26 October audit confirmed these limitations and
other native-reference/conditional-validation gaps; passing old tests did not
establish creative workflow parity. The 0.4 implementation specifically addresses
them and requires the acceptance gate above.

## Retained discovery scope

The 25 October snapshot has 274 operations, 273 wire IDs, 21 providers, 64 LLM
IDs in the documentation/discovery union (55 live-listed in that check) and 1,063
fixed Effects from 1,088 records. Discovery used read-only authenticated balance,
LLM inventory and Effects endpoints. Five representative public CRUN schemas were
rechecked during the 26 October audit and matched structurally. These counts and
samples are not proof of present entitlement, all-catalog freshness or paid execution.

## Known limitations

- The one approved Nano Banana Pro image task completed. Live native-reference
  uploads, video/audio generation, refund behavior and other model/account
  availability remain Not Checked; one successful task does not validate a catalog.
- Complex nested media, GIF-specific source adapters, 3D-native results, LLM
  execution and provider cancellation remain incomplete. Unknown Vidu output types
  stay Advanced instead of promising the wrong native output.
- Some restrictions exist only in provider prose. Current schema and explicit
  guards do not prove every model/reference combination.
- Reuse is local and credential/request/Take scoped. Deleting/rolling back history,
  changing credentials/configuration or losing assets must not be treated as a
  provider-enforced exactly-once guarantee. Preserve accepted task IDs.
- A positive optional cap checks the estimate, not the final provider bill.
  Displayed receipts are historical; account balance is independently checked.
- Other interactive operating systems, remote/multi-user servers and Comfy
  Registry publication are not established by this release's local validation.

Runtime packaging uses an explicit allowlist and CRC/SHA256 checks. Keys, private
journals/indexes, user assets, signed URLs and Git history are excluded.
