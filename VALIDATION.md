# 0.4.2 native-media creative workflow validation

Evidence reviewed for the 0.4.2 public release on **5 November 2026**. The checks
below retain their actual execution dates: 26 October implementation/release
checks, the 26 October 0.4.1 panel check and the 27 October live H3 test, all on
Windows. Live generations were not repeated on 5 November. Release-wide offline
checks below were rerun; public CI and publication results are verified separately.

## 0.4.2 release checks — 5 November 2026

- Python suite: 250 tests, 249 passes and one Unix-only permission skip on
  Windows, using Comfy's Python 3.13 environment.
- Frontend suite: 43 passes, including node panel width and resize handling.
- No live generation or paid provider task was submitted for this release check.
- Runtime ZIP uses the explicit package allowlist, CRC and SHA256 verification.
  GitHub CI and Comfy Registry version status are external publication gates;
  this file does not claim approval before those services report it.

## Current 0.4 implementation

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

## Retained 0.4.0 release evidence — 26 October 2026

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
| Interactive browser/canvas at 0.4.0 release | Not checked then | Computer Use stopped because it could not reliably determine the active browser URL; later scoped checks are recorded below |
| Runtime ZIP/install integrity | Release gate | Explicit allowlist, CRC/SHA256, saved-key scan and installed-file/KIE/credential checks run before publication |
| GitHub CI | Release gate | Windows/Ubuntu workflow results on the release commit are authoritative; prior-release success is not used |
| Live video/audio generation at 0.4.0 release | Not checked then | Later approved H3 upload/video test is recorded below; live audio and other models remain unverified |

The real image test is provider execution evidence for that model/settings only.
Synthetic video/audio prove native media integration and saving; the later H3
check below provides separate upstream video acceptance evidence. Financial
receipts are private; the public package contains no account balance, key, task
ID, user-media reference or private journal.

## 0.4.1 panel verification — 26 October 2026

- Both model-help and credit-receipt panels follow the node width during draw and
  resize. Text can scroll within the panel, while the Advanced button stays visible.
- All 43 frontend tests passed for that patch. In a separate Comfy canvas using
  frontend 1.55.18, the MiniMax H3 Image to Video node was inspected while resizing
  and opening Advanced controls.
- The original oversized-panel report was not reproduced in that separate
  session before the change. The scoped visual check passed; it does not establish
  confirmation in the original user workflow.

## Live H3 video verification — 27 October 2026

An explicitly approved single test ran through the **installed CRUN extension**
in an isolated local Comfy workflow:

```text
Load Image → CRUN MiniMax H3 — Image to Video → Save Video
```

| Check | Status | Evidence |
| --- | --- | --- |
| Native reference upload | Pass, one path | Connected first-frame IMAGE uploaded through the CRUN node's Estimate/Generate flow |
| Live H3 generation | Pass, one configuration | `minimax/h3-i2v`; five-second request, 480P, standard speed, no last frame |
| Quote and charge | Pass, one task | Quote and provider-reported actual task charge were both 12.5 CRUN credits |
| Receipt display | Pass | Node displayed quote, actual credits and a separately timestamped balance check; private account balance/receipts are excluded from this package |
| Native VIDEO and Save Video | Pass | The connected Save Video node saved H.264 MP4; decoded locally as 480 × 480, 24 fps, 124 frames |
| Visual inspection | Pass, scoped | The saved clip's sampled frames showed the requested rotation of the reference subject |

This is a standard CRUN H3 test, not evidence for an independently identified
H3 Max Turbo variant. It proves one image-upload → model → native VIDEO → Save
Video path. It does not validate every video model/reference mode, live audio,
refunds or cancellation behavior. No task identifier, signed URL, account balance
or user-media reference is included in this public evidence.

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

- The approved Nano Banana Pro image task and one MiniMax H3 first-frame upload/
  video task completed. Other live reference modes, video models, audio generation,
  refund behavior and model/account availability remain Not Checked; these two
  paths do not validate a catalog.
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
- Other interactive operating systems and remote/multi-user servers remain
  unverified. Registry submission/review and GitHub release status must be checked
  independently; local validation does not establish public availability.

Runtime packaging uses an explicit allowlist and CRC/SHA256 checks. Keys, private
journals/indexes, user assets, signed URLs and Git history are excluded.
