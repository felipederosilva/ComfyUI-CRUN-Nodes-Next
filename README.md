# CRUN Nodes Next

An independent **CRUN integration for ComfyUI**, by Felipe Silva. Built on the
lessons of [KIE Nodes Next](https://github.com/felipederosilva/ComfyUI-KIE-Nodes-Next),
with separate credentials, code, node IDs and installation. This project is not
affiliated with CRUN or Comfy Org.

## 0.4.0 — native media workflows

A normal video node now returns **VIDEO directly**. Image nodes return **IMAGE
and MASK**; speech/music nodes return **AUDIO**. Connect these outputs to Comfy's
Preview/Save nodes. The creative node submits, waits for its existing task,
downloads the selected result, and returns usable native media.

```text
Load Image / Load Video / Load Audio
                  |
       CRUN task + model version
                  |
          IMAGE / VIDEO / AUDIO
                  |
             Preview / Save
```

The main menu presents task-focused Studio families, Effects and AI Tools whose
output type is known. Family dropdowns retain each model's own fields, choices,
reference roles and limits. Advanced URL/JSON inputs remain secondary. Switching
a model returns the action to Prepare and preserves any positive credit cap.

Native reference roles include first/last frames, image batches, masks, motion
video, source video and ordered video/audio references where the documented
simple fields are supported. For example, Kling Motion Control accepts a native
motion VIDEO, and Seedance Reference to Video exposes ordered VIDEO/AUDIO ports.
These adapters do not make every provider's similarly named model interchangeable.

**A real image round trip has passed:** one approved Nano Banana Pro 1K test
created, downloaded, decoded and saved native IMAGE/MASK media for a confirmed
8-credit charge. Its completed asset reopened locally without a provider request.
Actual Comfy executor checks also passed for Save Image, synthetic VIDEO to
Save Video and synthetic AUDIO to Preview Audio. These checks do not prove live
video/audio generation or every model. See [VALIDATION.md](VALIDATION.md).

## Start with a Studio workflow

Open a `Studio-` recipe in Comfy's template library or from
[example_workflows](example_workflows). Choose the task and model version, then
load media into its named reference roles. Known typed Model/Effect/Tool recipes
also end in the appropriate Preview/Save path. Preparation-only and unknown-output
operations remain Advanced API examples; their presence is not a working-media claim.

1. **Prepare** validates and encodes locally. It never uploads, quotes, reads a
   balance or creates a task. Validation/status feedback explains missing inputs;
   downstream media is blocked until an actual result exists.
2. **Estimate** uploads required native references and asks CRUN for a quote. It
   does not create a generation. Review the model, settings, reference transmission
   and cost before running Generate.
3. **Generate** validates, uploads required media, quotes, checks any active cap
   and available balance, and submits once for a new request/Take. It then waits,
   saves the selected result locally and supplies its native output.
4. **Reuse a Take:** the same prepared request and Take use the recorded task
   instead of submitting another one. Increase **Take** only when intentionally
   requesting a new paid result. Changing model, settings, references or Take
   changes the request; do not assume the same Take number freezes all edits.
5. **Resume after interruption:** rerun the same unchanged request/Take, or paste
   the accepted ID into **Resume existing task** under Advanced. In Estimate or
   Generate, explicit resume retrieves that ID without the old prompt/reference
   files, upload, quote or new submission. Native references are lazy during explicit
   recovery; disconnect any missing-file source nodes if Comfy rejects their own
   file validation before execution. Prepare always remains local.

Native connections and advanced URL fallbacks cannot both fill the same field.
Ordered numbered references start at slot 1 without gaps. Unsupported connections
are preserved and reported, rather than silently removed when selecting a model.
Some nested reference structures and GIF-specific inputs still require their
original URL/JSON format.

Normal creative generators run through a connected Preview/Save output path;
they are not independent full-graph output targets. Legacy **API task** nodes
retain their old behavior and output positions under Advanced for compatibility.
Existing graphs are not silently converted to a different output contract.

## Task reuse and recovery

Creative submission records live outside the extension. A keyed request digest
scopes reuse to the configured API key, prepared request and Take. A cross-process
submission lock coordinates Comfy processes sharing the same config directory.
Accepted task IDs are recorded before waiting for completion. Unknown submission
outcomes stop and require inspecting CRUN Logs; no replacement is submitted
automatically.

The creative-job history does **not automatically evict** old mappings: they also
prevent an old Take from creating another paid task after restart. A full or
unreadable history stops new generation rather than silently resetting it. Keep
a backup of this history with your task IDs. Changing API keys or config folders,
or deleting history, must not be treated as preserving automatic deduplication.
These are local safeguards, not a provider-wide exactly-once guarantee.

Completed assets are stored in `output/CRUNResults` with a credential-scoped local
index and content-hash checks. If a valid local copy is available, retrieval can
reuse it without downloading the provider's temporary URL again. Creative
completion may still make a read-only balance refresh. Missing/corrupt local
files fall back to retrieval of the same task ID, never a replacement generation.

Get Image/Video/Audio Result nodes remain available for separate existing-task
recovery. A timeout or download failure preserves the accepted ID. Stopping local
waiting does not promise remote cancellation or a refund.

## Outputs, credits and transparency

Creative outputs include the native media, URL, task ID, estimated credits,
actual credits, remaining balance and diagnostic JSON. IMAGE nodes additionally
return MASK using Comfy's transparency convention: **1 minus alpha**. An opaque
result has a zero mask; invert it if your downstream tool expects an opaque-subject
matte. Mask output is not a claim of model-generated layer decomposition.

The receipt distinguishes:

- **Estimated credits:** CRUN's quote before submission.
- **Actual credits:** the completed task's provider-reported cost, if available.
- **Credits left:** a separate timestamped balance check after completion.

An unknown cost or balance is unavailable, not zero. Account-balance changes are
never used to invent the actual cost of one task. Quotes and displayed balances
are historical responses, not continuously live prices or balances.

The optional estimated-credit cap is under **Show advanced controls**.
`crun_max_credits=0` disables that optional cap; a positive saved cap remains in
force, including through model changes. A reference upload can precede the quote,
cap or balance rejection. The cap checks the estimate; it is not a provider-enforced
limit on the final bill. There are no extra upload/paid checkboxes in the simple flow.

## Install or update

Use the backend ComfyUI folder containing `main.py` and `custom_nodes`, not the
Desktop program/resources directory. Obtain source here or a package from
[Releases](https://github.com/felipederosilva/ComfyUI-CRUN-Nodes-Next/releases).

1. Close Comfy Desktop.
2. Move the previous CRUN folder to a backup **outside custom_nodes**; Comfy can
   import backups left inside its scanning directory.
3. Extract to `ComfyUI/custom_nodes/ComfyUI-CRUN-Nodes-Next`, with `__init__.py`
   directly inside and no extra nested repository folder.
4. Install `requirements.txt` with **Comfy's Python** if needed. The package uses
   requests, aiohttp, Pillow and NumPy; a current Comfy runtime supplies PyTorch,
   PyAV and the native VIDEO API for media adapters.
5. Start Comfy, refresh the interface, and open **Settings → CRUN Next → Connection**.
   Use **Paste / replace CRUN API key**, **Save key**, then **Check connection**.
6. Open the CRUN Next launcher for Models, AI Effects and AI Tools, or search
   **CRUN** in the Nodes menu. Use the ordinary Studio/task nodes for native media.

Legacy individual task IDs remain under **Advanced → API Tasks**. Old family IDs
remain under **Advanced → Legacy Families**. Typed individual model nodes are
under **Advanced → Individual Models**; Studio families are the main creative entry.
LLM execution, 3D-native results and Effects with unknown output types remain
Advanced and are not presented as complete typed workflows.

The helper below is **first-install-only**: it requires an explicit backend path,
refuses an existing destination, copies an allowlist and verifies hashes. It does
not install dependencies or start Comfy.

```powershell
python scripts/install.py --custom-nodes "C:\path\to\ComfyUI\custom_nodes"
```

## Catalog snapshot and readiness

The retained snapshot was collected on **25 October 2026**:

| Inventory | Bundled coverage |
| --- | --- |
| Model/operation definitions | 274 entries, including 273 exact wire IDs across 21 providers |
| LLM discovery union | 64 IDs: 55 listed by the authenticated check, 9 documentation-only |
| Fixed AI Effects | 1,063 unique templates from 1,088 source records |
| AI Tools | 18 documented operations, included above |
| Image/video family tasks | 62 families covering 162 operations |
| Workflow inventory | 1,399 Model/Effect/Tool/Studio recipes, all defaulting to Prepare |

Counts mean discovered operations/templates, not distinct model engines,
entitlement or successful execution. In 0.4, known-output recipes use native media
paths; unsupported protocols or unknown outputs stay explicitly Advanced. No
account access or generated quality is inferred from a catalog listing.

Sources are CRUN's [documentation index](https://docs.crun.ai/llms.txt), public
model definitions, the [LLM table](https://docs.crun.ai/models/llm-list) and the
[live LLM inventory contract](https://docs.crun.ai/models/llm/quickstart). Refresh is
explicit. Public schema refresh uses no key; Effects and live LLM discovery use
separate read-only authenticated requests. Restart Comfy after registering new
catalog definitions. Never put a secret on a command line or in a workflow.

```powershell
python scripts/sync_catalog.py
python scripts/sync_effects.py --comfy-root "C:\path\to\ComfyUI"
python scripts/build_templates.py
python scripts/build_family_templates.py
```

## Credentials and privacy

Enter your own [CRUN key](https://crun.ai/user-api-key) only in CRUN Next settings.
Keys are never stored in workflow JSON, browser localStorage or persistent Comfy
setting values. Windows uses DPAPI for the current user, without plaintext
fallback. Other platforms use an owner-readable file that is not encrypted.
`CRUN_API_KEY` overrides saved storage. Removing a saved key does not unset it.

Configuration, connection receipts, catalog caches, task records and completed
asset indexes are separate files outside the extension. `CRUN_NEXT_CONFIG_DIR`
can select another config directory. Upload URLs are cached only in memory for
30 minutes by content and credential; they are temporary, not durable storage.
Request digests and task records omit prompts, media URLs and keys, but generated
files and diagnostic node outputs can still contain private material. Review
saved workflows before sharing.

The bridge targets a trusted single-user loopback installation. DPAPI does not
protect against compromised same-user processes/custom nodes. Optional remote
previews load on user action and reveal the browser IP to their media host. No
proprietary Effects implementation or provider preview bundle is included.
See [SECURITY.md](SECURITY.md).

## Development and remaining gates

```powershell
python -m unittest discover -s tests -v
node --test tests/*frontend*.mjs
python scripts/build_release.py
```

[VALIDATION.md](VALIDATION.md) separates prior discovery, offline/synthetic checks,
real local media, interactive Comfy acceptance and live provider execution.
[ROADMAP.md](ROADMAP.md) lists the remaining model/media and release gates. Comfy
Registry publication is not submitted by this code change.

MIT license. KIE Next remains independent; neither package routes requests through
the other. Remote models/templates remain subject to CRUN's terms and charges.
