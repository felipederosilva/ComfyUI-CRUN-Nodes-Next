# 0.3.1 configuration preflight and creative-node alpha validation

Checked on Windows, 25 October 2026.

## 0.3.1 reported-error regression

- Reproduced the reported Seedance setup: generate, paid permission true, credit
  ceiling 0 and a connected image with uploads disabled.
- Actual Comfy queue validation now rejects that setup before execution and
  combines the budget and upload requirements in its response.
- Verified that ordinary model enum validation and IMAGE/MASK link-type checks
  still reject invalid inputs. Local prepare with a native image still succeeds.
- The update chooses no credit limit, changes no workflow permissions, and makes
  no paid submissions or reference uploads during validation.

## Verified offline

- 183 Python tests: 182 passed and one Unix-only permission test skipped in the
  Comfy Python environment. Torch-dependent checks skip when Torch is absent in CI.
- 23 JavaScript tests passed, including switching every bundled family/profile,
  enum/range updates, whole-number rendering, hidden seed controls and connection retention.
- 62 task-focused family nodes cover 162 image/video operations. Each selected
  model dispatches its exact documented ID and validates its own parameter schema.
- All 62 Studio recipes connect task IDs to native result retrieval and Preview
  Image / Save Video. The 1,337 per-option recipes are retained with native IMAGE
  source connections where roles are known. All 1,399 start in prepare mode,
  upload/paid permissions false and credit ceiling zero.
- Native IMAGE/MASK encoding: ordered batches, finite normalized values, PNG
  pixels, alpha/grayscale, image/count/byte limits and matching mask dimensions.
- First/last-frame pairs, ordered Effect images, reference-image batches,
  inpainting masks, face references and background images have appropriate sockets.
  Array alternatives in Flux and Wan schemas are handled explicitly.
- Uploads require permission. A separate credential-free PUT transports bytes;
  no redirects or retries. Temporary receipts are cached in memory by credential
  and content for 30 minutes, without persisting the cache.
- Preparation placeholders cannot be submitted or quoted as real URLs. Invalid
  parameters and ambiguous native/URL sources stop before an upload.
- Paid submission still requires permission, a positive estimate ceiling, an
  estimate and sufficient balance. A single task ID is journaled; ambiguous
  submission failures instruct recovery without automatic resubmission.
- Retrieval tests poll only the existing task ID, preserve it on failure/timeout,
  bound downloads, omit credentials and save media under output/CRUNResults.
- Real local PNG-to-Torch decoding and a synthetic MP4 loaded through Comfy's
  native VideoFromFile implementation (64 x 48) verified media adapters locally.

## Actual ComfyUI interface and execution

- Isolated CPU-only ComfyUI 0.42.5 / frontend 1.55.18 starts with CRUN Next.
- Imported Studio-Seedance-Image-to-Video through Comfy's template browser.
- Confirmed Load Image -> first_frame, the eight-option Seedance dropdown,
  optional last_frame, model-specific settings, Get Video Result and Save Video.
- Switched Seedance 2.5 to 2.0 in the real canvas: connections remained intact,
  supported controls updated and execution reset to prepare. Advanced fields
  stay secondary. The final interface renders integer durations without decimals.
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
  was performed for 0.3. Mocked transport success and local media are not evidence
  of a provider round trip or access to every upstream model.
- Native VIDEO/AUDIO input uploads, complex nested 3D/multi-face references,
  LLM execution and cancellation remain pending. Advanced URL/JSON inputs remain
  available where these native adapters do not exist.
- Provider prose may impose additional image dimensions, file formats, reference
  roles and conditional requirements. Machine schemas cannot prove every combination.
- Upload URLs are temporary. Retry result retrieval by task ID after a timeout;
  do not regenerate automatically. Original files should remain available locally.
- Custom URL connections to a field renamed with an _urls suffix may need to be
  reconnected; existing per-option node IDs and widget-value order are retained.
- Other interactive operating systems, shared/public Comfy servers and Comfy
  Registry publication have not been exercised for this release.

Runtime packaging uses an explicit allowlist plus CRC/SHA256 checks. Credentials,
user caches, task journals, signed upload links and Git history are excluded.
