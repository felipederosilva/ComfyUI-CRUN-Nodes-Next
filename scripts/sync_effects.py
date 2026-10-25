"""Refresh public template metadata through authenticated read-only CRUN APIs.

Never prints credentials, creates a task or uploads any media. Only catalog
metadata is written. Account/task/balance information is deliberately excluded.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _public_metadata(value):
    if isinstance(value, dict):
        return {str(key): _public_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_metadata(item) for item in value]
    if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
        try:
            parsed = urlsplit(value)
            # Do not commit account-scoped signed/download links. Plain public
            # previews can be discovered again from the live catalog in Comfy.
            if parsed.query or parsed.fragment or parsed.username or parsed.password:
                return None
        except ValueError:
            return None
    return value


def _fetch_catalog(client, provider: str) -> dict:
    """Read every documented page, refusing silently incomplete snapshots."""
    rows, seen, total = [], set(), None
    for page in range(1, 101):
        payload = client._request("GET", f"/api/v1/client/job/{provider}-templates", params={"page": page, "page_size": 50})
        if not isinstance(payload, dict) or not isinstance(payload.get("templates"), list):
            raise ValueError("Effects catalog has an unsupported page format.")
        reported = payload.get("total")
        if not isinstance(reported, int) or isinstance(reported, bool) or not 0 <= reported <= 5000:
            raise ValueError("Effects catalog did not report a bounded total.")
        if total is None:
            total = reported
        elif total != reported:
            raise ValueError("Effects catalog changed during discovery. Retry explicitly.")
        page_rows = payload["templates"]
        signature = json.dumps(page_rows, sort_keys=True, ensure_ascii=False)
        if signature in seen and page_rows:
            raise ValueError("Effects endpoint repeated a page before completion.")
        seen.add(signature)
        rows.extend(page_rows)
        if len(rows) >= total:
            if len(rows) != total:
                raise ValueError("Effects catalog returned inconsistent totals.")
            return {"total": total, "templates": rows}
        if not page_rows:
            raise ValueError("Effects pagination ended before the reported total.")
    raise ValueError("Effects catalog exceeds the supported pagination limit.")


def refresh(output: Path) -> dict:
    from crun.client import CRUNClient
    from crun.effects import normalize_catalog, _https_url

    client = CRUNClient()
    providers = {}
    for provider in ("kling", "bytedance", "vidu"):
        payload = _fetch_catalog(client, provider)
        cards = normalize_catalog(provider, payload)
        identifier_key = {"kling": "key", "bytedance": "TemplateId", "vidu": "template"}[provider]
        grouped = {}
        for row in payload["templates"]:
            if not isinstance(row, dict) or not row.get(identifier_key):
                raise ValueError("An Effects template has no documented identifier.")
            grouped.setdefault(str(row[identifier_key]), []).append(row)
        if {card["id"] for card in cards} != set(grouped):
            raise ValueError("Some Effects templates could not be identified; snapshot was not replaced.")
        for card in cards:
            variants = grouped[card["id"]]
            if len(variants) > 1:
                card["raw"]["catalog_variants"] = variants
            if provider == "vidu":
                card["category"] = str(card["raw"].get("category_name") or card["category"])
                card["preview_url"] = _https_url(card["raw"].get("video"))
        providers[provider] = {
            "source": f"https://docs.crun.ai/templates/{provider}-template-list",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "live_read_only",
            "total": payload["total"],
            "total_records": payload["total"],
            "unique_templates": len(cards),
            "complete": True,
            "cards": _public_metadata(cards),
        }
    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contains_credentials": False,
        "generation_performed": False,
        "providers": providers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix=".effects-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {provider: {"unique_templates": len(value["cards"]), "catalog_records": value["total_records"]} for provider, value in providers.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, help="Optional ComfyUI root to resolve that profile's credential store.")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "effects.json")
    args = parser.parse_args()
    if args.comfy_root:
        comfy = args.comfy_root.resolve()
        if not (comfy / "folder_paths.py").is_file():
            parser.error("--comfy-root must contain folder_paths.py")
        sys.path.insert(0, str(comfy))
    try:
        counts = refresh(args.output.resolve())
    except Exception as error:
        # CRUN client errors are sanitized already, but avoid echoing an unknown
        # exception that could include request state or a credential path.
        print(f"Effects refresh failed ({type(error).__name__}). Existing metadata was not replaced.", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "providers": counts, "total_templates": sum(value["unique_templates"] for value in counts.values()), "generation_performed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
