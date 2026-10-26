# 0.3.2 simple actions and credit-receipt alpha validation

Checked on Windows, 25 October 2026.

## 0.3.2 reported-error regression and approved action flow

- Prepare remains local: connected media is inspected/encoded without uploading,
  requesting a quote, querying a balance or creating a task.
- Estimate uploads required connected references and requests a quote. Generate
  uploads required references, quotes, checks any positive optional cap and the
  available balance, then submits one task. The selected action replaces the
  extra upload/paid checkboxes; their serialized arguments remain accepted for
  compatibility but no longer gate these actions.
- The optional estimated-credit cap lives under Advanced. Zero disables that cap;
  existing positive caps, including 100 credits, are preserved across model
  changes. Negative, nonnumeric and nonfinite caps remain invalid.
- A synthetic quote above a saved 100-credit cap returns the exact quote and cap
  with status budget_blocked and an empty task ID. It does not query the balance,
  create a task or write a submission marker. This fixture is not the reported
  user's actual quote or evidence of a live CRUN price.
- Insufficient balance also returns a readable receipt with an empty task ID.
  These outcomes no longer raise a budget/balance traceback. Empty-ID result
  retrieval safely waits instead of attempting a download or regeneration.
- The node receipt displays returned quote metadata, optional cap, model/time
  and balance at check when available. It labels the quote as an estimate rather
  than final credits spent; it makes no network requests or workflow changes.
- Explicit Comfy input-validation signatures retain normal model enum and
  IMAGE/MASK link-type checks. Legacy checkbox values do not override the action.

## Verified offline

- 187 Python tests completed in the Comfy Python environment: 186 passed and one
  Unix-only permission test skipped. Torch-dependent checks skip when Torch is
  absent in CI.
- 34 JavaScript tests passed: 11 main frontend checks, 14 model-control checks and
  nine credit-receipt checks. They cover family/profile switching, enum/range
  updates, integer rendering, hidden legacy checkboxes, positive-cap retention,
  preserved connections, receipt parsing/rendering and callback cleanup.
- 62 task-focused family nodes cover 162 image/video operations. Each selected
  model dispatches its exact documented ID and validates its own parameter schema.
- All 62 Studio recipes connect task IDs to native result retrieval and Preview
  Image / Save Video. The 1,337 per-option recipes retain native IMAGE source
  connections where roles are known. All 1,399 start in prepare mode with optional
  cap zero. Legacy false checkbox slots remain for workflow compatibility.
- Native IMAGE/MASK encoding covers ordered batches, finite normalized values,
  PNG pixels, alpha/grayscale, image/count/byte limits and matching mask dimensions.
- First/last-frame pairs, ordered Effect images, reference-image batches,
  inpainting masks, face references and background images have appropriate sockets.
  Array alternatives in Flux and Wan schemas are handled explicitly.
- Reference uploads follow the selected Estimate/Generate action. A separate
  credential-free PUT transports bytes without redirects or retries. Temporary
  receipts are cached in memory by credential/content for 30 minutes.
- Preparation placeholders cannot be submitted or quoted as real URLs. Invalid
  parameters and ambiguous native/URL sources stop before an upload. An upload
  can precede a quote/cap or balance rejection; that rejection means no generation
  was submitted, not that no provider request occurred.
- A valid Generate action with no optional cap can submit after quote and balance
  checks. Submission remains single-attempt with recoverable task IDs and local
  journaling; ambiguous failures instruct recovery without automatic resubmission.
- Retrieval tests poll only the existing task ID, preserve it on failure/timeout,
  bound downloads, omit credentials and save media under output/CRUNResults.
- Real local PNG-to-Torch decoding and a synthetic MP4 loaded through Comfy's
  native VideoFromFile implementation (64 x 48) verified media adapters locally.

## Actual 0.3.2 credit-receipt interface check

- Opened an isolated CPU-only ComfyUI 0.42.5 / frontend 1.55.18 instance and
  executed a QA-only receipt emitter from the real Run button. That fixture
  imports no provider client and cannot upload, quote or create a CRUN task.
- Confirmed the node displays its synthetic 250-credit quote, retained 100-credit
  optional cap, model/time, block explanation and Advanced instructions. The
  model and node title explicitly label the values as synthetic test data.
- Verified the extra upload/paid checkboxes stay hidden and Advanced exposes the
  saved optional cap. Increased the receipt height after the visual check so the
  explanation remains readable. No existing user workflow was changed.

## Retained family-interface and local execution checks

The following checks were performed during the preceding 0.3 development. They
verify the family interface and local Prepare path; they are not live-provider
or final 0.3.2 credit-widget execution evidence.

- Isolated CPU-only ComfyUI 0.42.5 / frontend 1.55.18 starts with CRUN Next.
- Imported Studio-Seedance-Image-to-Video through Comfy's template browser.
- Confirmed Load Image -> first_frame, the eight-option Seedance dropdown,
  optional last_frame, model-specific settings, Get Video Result and Save Video.
- Switched Seedance 2.5 to 2.0 in the real canvas: connections remained intact,
  supported controls updated and execution reset to prepare. Advanced fields
  stay secondary. Integer durations render without decimals.
- Selected a locally created synthetic PNG and ran the full graph from Comfy's
  Run button. It completed successfully with one native image, zero validation
  errors, an empty task ID and no provider activity. Empty-ID retrieval safely
  blocked preview/save and explained that nothing had been submitted.
- Saved QA baselines before opening templates. No existing user workflow was
  discarded. Screenshots show the isolated test fixture, not a paid generation.

## Retained discovery and credentials

- The reviewed 0.2 catalog snapshot remains: 274 operations, 273 wire IDs,
  21 providers, 55 live-listed LLM IDs in a 64-ID documentation/discovery union,
  and 1,063 unique Effects covering all 1,088 source records.
- That discovery used authenticated read-only balance/model/Effects endpoints.
  Version 0.3 development did not repeat paid/provider-media operations.
- Windows DPAPI persistence, safe historical connection/balance receipts and
  loopback/same-origin/nonce boundaries remain covered by tests.
- Per-option node IDs remain available. Image/video families are in the main
  menu; individual model definitions are retained under Advanced/Catalog.

## Not verified / remaining limitations

- No real CRUN upload, cost estimate, paid generation or generated-media download
  was performed by this development validation. Mocked transport success and local
  media are not evidence of a provider round trip or access to every upstream model.
- Native VIDEO/AUDIO input uploads, complex nested 3D/multi-face references,
  LLM execution and cancellation remain pending. Advanced URL/JSON inputs remain
  available where these native adapters do not exist.
- Provider prose may impose additional image dimensions, file formats, reference
  roles and conditional requirements. Machine schemas cannot prove every combination.
- The optional cap checks an estimate, not a provider-enforced final spending cap.
  Quote and balance receipts are historical responses, not continuously live data.
- Upload URLs are temporary. Retry result retrieval by task ID after a timeout;
  do not regenerate automatically. Original files should remain available locally.
- Custom URL connections to a field renamed with an _urls suffix may need to be
  reconnected; existing per-option node IDs and widget-value order are retained.
- Other interactive operating systems, shared/public Comfy servers and Comfy
  Registry publication have not been exercised for this release.

Runtime packaging uses an explicit allowlist plus CRC/SHA256 checks. Credentials,
user caches, task journals, signed upload links and Git history are excluded.
