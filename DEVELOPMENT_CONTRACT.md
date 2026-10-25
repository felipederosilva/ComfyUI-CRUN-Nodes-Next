# CRUN Next 0.1.0 development contract

This is an independent, unofficial ComfyUI custom-node project. No authenticated
provider request, upload or paid task is part of the initial validation.

## Component contracts

- `crun.settings`: `get_api_key()`, `save_api_key(value)`, `clear_api_key()`,
  `public_status()` with configured/source/key_hint/storage, `settings_path()`.
  Environment override is `CRUN_API_KEY`. Never return a full credential publicly.
- `crun.client`: `CRUNClient(api_key=None, session=None)`, `CRUNError`,
  `get_balance()` -> float, `get_task(task_id)` -> dict,
  `list_effects(provider)` -> dict (provider is kling/bytedance/vidu),
  `estimate_credits(model, input_payload)` -> dict. HTTP errors must not leak keys.
  No automatic resubmission of creation requests. No arbitrary API base override.
- `crun.effects`: `normalize_catalog(provider, payload)` -> list of cards;
  `build_effect_plan(provider, template_id, image_urls, options=None)` -> dict.
  Cards contain id/provider/name/category/cover_url/preview_url/credits/
  required_images/raw. Do not guess undocumented slot counts. No paid execution.
- `web/crun_next.js` imports `app` and `api` from `../../scripts/*`.
  Settings action opens an ephemeral password form; no key widget in a graph,
  localStorage, Comfy settings persistence, or workflow. No automatic HTTP actions
  except local status. Effects tab is on-demand; avoid loading remote previews
  automatically. DOM textContent, never untrusted HTML.

## Local server API

All paths are prefixed `/crun-next`. Requests are restricted to a loopback Comfy
server. `/status` returns safe state plus an in-memory `nonce`. All other requests
send `X-CRUN-Nonce` using that value; POSTs use JSON. Errors: `{ok:false,error}`.

- GET `/status` -> `{ok:true, version, configured, source, key_hint, storage, nonce}`
- POST `/credentials` body `{api_key}` saves locally (no remote validation).
- POST `/credentials/clear` clears the saved credential, not an environment key.
- POST `/connection` -> `{ok:true,balance,checked_at}` reads provider balance.
- POST `/effects/catalog` body `{provider}` -> `{ok:true,provider,cards,fetched_at}`
  fetches provider catalog once on explicit request; no generation.

Responses do not return API keys, auth headers or upstream raw exceptions.

## Initial scope

Connection/balance, read-only task inspection, non-generating cost estimation,
read-only Effects browser, and documented experimental effect-plan preparation.
All-model generation, native media upload and paid Effects execution are later
gated milestones. Do not market this skeleton as a complete model pack.
