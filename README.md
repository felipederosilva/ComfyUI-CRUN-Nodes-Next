# CRUN Nodes Next

An independent **CRUN integration for ComfyUI**, by Felipe Silva. Built on the
lessons of [KIE Nodes Next](https://github.com/felipederosilva/ComfyUI-KIE-Nodes-Next),
with separate code, credentials, node IDs and installation. Not affiliated with
or endorsed by CRUN or Comfy Org.

## 0.2.0 — model catalog, AI Effects and AI Tools

Explore CRUN models in Comfy, start from a workflow for each option, and prepare
a request with that model's documented fields. Compatible media tasks can be
submitted through an explicit generation gate. **No real paid generation has
been tested in this release.** Native uploads, automatic polling and result
preview/download/save are not implemented yet.

The bundled snapshot was collected on **25 October 2026**:

| Inventory | Bundled coverage |
| --- | --- |
| Model/operation definitions | 274 entries, including 273 exact wire model IDs across 21 providers |
| LLM definitions | 64 IDs in the documentation/live-discovery union: 55 listed by the authenticated check, 9 documentation-only |
| Individual AI Effects | 1,063 unique templates: Kling 226, ByteDance 341, Vidu 496 |
| Effects source records | 1,088 records; repeated template IDs share a node with retained variants |
| AI Tools | 18 documented tools, included in the model/operation definitions above |
| Generated catalog nodes and starter workflows | 1,337 of each |
| All registered nodes | 1,344, including 7 setup/utility nodes |

These counts describe discovered definitions, not tested execution or access for
every CRUN account. Documentation-only LLMs are explicitly labeled as not listed
by the discovery check. LLMs and operations with dedicated protocols are
**prepare-only**. Current media references require public HTTPS URLs.

![CRUN Next connection workspace](docs/screenshots/connection.png)

## Install or update

Use the backend ComfyUI folder containing `main.py` and `custom_nodes`, not the
Desktop program/resources directory. Obtain source from this repository or an
available package from [Releases](https://github.com/felipederosilva/ComfyUI-CRUN-Nodes-Next/releases).

1. Close Comfy Desktop.
2. For an update, move the previous CRUN extension folder to a backup location
   **outside custom_nodes**. Comfy can import backups left inside that directory.
3. Extract into `ComfyUI/custom_nodes/ComfyUI-CRUN-Nodes-Next`, with
   `__init__.py` directly inside. Avoid an extra nested repository folder.
4. If needed, install `requirements.txt` with **Comfy's Python**. The package
   requires `requests` and `aiohttp`.
5. Start Comfy and refresh the interface. Open **Settings → CRUN Next → Connection**.
   Use **Paste / replace CRUN API key**, **Save key**, then **Check connection**.
6. Open the **CRUN Next** launcher or **Extensions → CRUN Next** for **Models**,
   **AI Effects** and **AI Tools**. Search **CRUN** in the Nodes menu.

The four native settings rows expose key entry, a safe saved-key summary,
connection state and balance. Saved status is historical; use a live check to
confirm the current key/balance. Credentials live outside the extension package.

The optional helper is **first-install-only**:

```powershell
python scripts/install.py --custom-nodes "C:\path\to\ComfyUI\custom_nodes"
```

It requires the explicit backend path, refuses an existing destination, copies an
allowlist and verifies hashes. It does not install dependencies or start Comfy.

## Start with a catalog workflow

Open a matching JSON from [example_workflows](example_workflows). The manifest
maps each starter to its entry and node type. Each model, tool and unique Effects
template has an individual node; required inputs, choices and limits come from
its schema. Arrays and objects use JSON fields.

1. Keep `crun_mode=prepare`, `crun_allow_paid_generation=false` and
   `crun_max_credits=0`. Fill the fields and run to inspect the payload and
   validation errors locally. No provider request is made.
2. For a supported media operation, select `estimate` to request a quote without
   creating a job. Review the model, references, parameters and estimated credits.
3. To submit intentionally, select `generate`, enable paid permission and set a
   positive maximum-credit ceiling. The node gets a fresh estimate, checks budget
   and balance, then submits **once**. This ceiling checks the estimate; it is
   not a provider-enforced cap on the final bill.
4. Keep the returned `task_id`. Use **Inspect Existing Task** to check the same
   task manually. Automatic polling, downloading and native media outputs are
   not implemented.

On timeout or an unknown submission outcome, inspect CRUN's task logs before
submitting again. There is no automatic retry. A local journal keeps submission
markers/task IDs without prompts, media URLs or keys. Disarm generation before
editing or sharing a workflow: another execution of an armed node can create
another paid job.

Some conditional requirements, file limits and template slot meanings appear
only in provider prose. Review the linked documentation; a schema is not proof
that every parameter combination works. Native files are not uploaded implicitly.

## Credits and utility nodes

- **Connection Status** reads safe local configuration without contacting CRUN.
- **Credits** reads balance and prints it in Comfy's console.
- **Effects Catalog** reads one provider's live metadata for inspection.
- **Prepare Effect Plan (Draft)** prepares an offline payload.
- **Estimate Credits (No Generation)** requests a model/input quote.
- **Inspect Existing Task** reads status/cost without creating another job.
- **AI Tools Catalog** lists the documented tools and input definitions; individual
  tool nodes exist under **CRUN Next → AI Tools**.

Read-only utility requests can repeat when queued. CRUN credits are separate from
KIE and Comfy credits. Task cost is reserved while pending/running and actual
after success/failed according to [CRUN's task contract](https://docs.crun.ai/models/common/get-task-info).
Missing cost is shown as unavailable, not zero. Shared balance changes are not
used to infer an individual task's actual cost.

## Catalog sources and refresh

Sources are CRUN's [documentation inventory](https://docs.crun.ai/llms.txt),
English model OpenAPI definitions, the [LLM documentation table](https://docs.crun.ai/models/llm-list)
and the documented [live LLM inventory](https://docs.crun.ai/models/llm/quickstart).
Exact IDs come from schemas/discovery, never marketing names or page slugs.
Endpoint, protocol, source and availability labels remain attached to entries.

The workspace refresh is an explicit action; opening the catalog does not
contact CRUN. Public definitions come from documentation without credentials.
When a configured key is used for live LLM discovery, the separate authenticated
GET reads inventory only and preserves its distinct availability labels.
The Effects template snapshot has its own read-only sync. Restart Comfy after a
catalog refresh to register changed node definitions. Caches are separate from
credentials; source errors remain visible.

Developer commands, from a source checkout:

```powershell
python scripts/sync_catalog.py
python scripts/sync_effects.py --comfy-root "C:\path\to\ComfyUI"
python scripts/build_templates.py
```

Public model sync does not itself query account availability. Effects sync uses
the locally configured key for catalog GETs. Never pass a secret on the command
line. Review source labels/counts before publishing regenerated metadata.

## Credentials and privacy

Create your own key at [CRUN API keys](https://crun.ai/user-api-key) and enter it
only in CRUN Next settings. It is sent to the local backend and is never saved in
workflow JSON, browser localStorage or persistent Comfy setting values.

Windows keys use **DPAPI for the current user**, without plaintext fallback.
Other platforms use an owner-readable file that is **not encrypted**.
`CRUN_API_KEY` overrides saved storage; removing a saved key does not unset it.
Configuration is in Comfy's user area or the platform user config directory.
`CRUN_NEXT_CONFIG_DIR` can select a separate location outside Git. Credentials,
connection receipts, catalog caches and task journal are separate files.

The bridge is **loopback-only**, intended for a trusted single-user installation.
DPAPI protects data at rest; another custom node or compromised same-user process
can still access secrets or submit requests. Optional external previews load on
user action and reveal the browser's IP to the media host. No third-party preview
files or proprietary Effects implementation is bundled. Treat workflows with
private media links as sensitive. See [SECURITY.md](SECURITY.md).

## Development and verification

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend*.mjs
python scripts/build_release.py
```

Read-only authenticated balance, LLM inventory and Effects discovery were
exercised. Offline tests/schema coverage do not prove paid generation or every
model's output quality. **No paid job, native upload or generated-media round
trip has been tested.** [VALIDATION.md](VALIDATION.md) records actual checks.
See [ROADMAP.md](ROADMAP.md) for next gates. Comfy Registry is not submitted.

MIT license. KIE Next remains independent; neither package imports, overwrites
or routes requests through the other. Remote models/templates remain subject
to CRUN's service terms, availability and charges.
