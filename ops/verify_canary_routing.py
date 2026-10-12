#!/usr/bin/env python3
"""Real LiteLLM weighted Canary request verifier, no synthetic success results.

Uses x-litellm-model-id to identify which *deployment ID* served each real
OpenAI-compatible request. Never stores prompts, completions or Bearer keys.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class CanaryCheckError(ValueError):
    pass


def origin_only(url: str) -> str:
    o = urlparse(url)
    if o.scheme not in ("http", "https") or not o.netloc or o.username or o.password or o.query or o.fragment or o.path not in ("", "/"):
        raise CanaryCheckError("gateway must be an HTTP(S) origin without credentials or URL parameters")
    return url.rstrip("/")


def request(url: str, key: str, *, payload: dict | None = None, timeout: float = 15.) -> tuple[dict, dict]:
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    req = Request(url, headers=headers, data=body,
                  method="POST" if body is not None else "GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            headers_out = {name.lower(): value for name, value in response.headers.items()}
            raw = response.read(8 * 1024 * 1024)
            if response.status != 200:
                raise CanaryCheckError(f"unexpected HTTP status: {response.status}")
    except HTTPError as exc:
        raise CanaryCheckError(f"LiteLLM returned HTTP {exc.code}") from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise CanaryCheckError("Gateway request failed or timed out") from exc
    try:
        content = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CanaryCheckError("Gateway did not return OpenAI-compatible JSON") from exc
    if not isinstance(content, dict):
        raise CanaryCheckError("Gateway response is not a JSON object")
    return headers_out, content


def owned_model_ids(model_info: dict, group: str) -> dict[str, str]:
    rows = model_info.get("data")
    if not isinstance(rows, list):
        raise CanaryCheckError("LiteLLM /model/info must include a data array")
    managed = {}
    for row in rows:
        if row.get("model_name") != group:
            continue
        info = row.get("model_info") or {}
        meta = info.get("metadata") or {}
        if not isinstance(meta, dict) or meta.get("owner") != "modelops":
            raise CanaryCheckError("Group contains a non-ModelOps deployment")
        slot = meta.get("slot")
        if slot not in ("stable", "canary") or slot in managed or not isinstance(info.get("id"), str):
            raise CanaryCheckError("Unrecognized / duplicate managed route")
        managed[slot] = info["id"]
    if not managed:
        raise CanaryCheckError("No managed LiteLLM routes for requested group")
    return managed


def verify(base: str, key: str, group: str, weight: int, count: int,
           transport=request) -> dict:
    if not key or not group or not (0 <= weight <= 100):
        raise CanaryCheckError("Valid key, group and candidate weight 0..100 required")
    if count < 100 or count > 20000:
        raise CanaryCheckError("At least 100 and at most 20000 real requests required")
    base = origin_only(base)
    _, body = transport(base + "/model/info", key)
    routes = owned_model_ids(body, group)
    if weight > 0 and "canary" not in routes:
        raise CanaryCheckError("Candidate model is missing from the live gateway")
    if weight < 100 and "stable" not in routes:
        raise CanaryCheckError("Stable model is missing from the live gateway")
    counts = {"stable": 0, "canary": 0}
    by_id = {v: k for k, v in routes.items()}
    first = time.monotonic()
    for _ in range(count):
        headers, result = transport(base + "/v1/chat/completions", key, payload={
            "model": group,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 8,
            "stream": False,
        })
        # Seeing the same model string in the body is not routing evidence.
        deployment = headers.get("x-litellm-model-id")
        if not deployment or deployment not in by_id:
            raise CanaryCheckError("Missing / unknown x-litellm-model-id deployment header")
        options = result.get("choices")
        if not isinstance(options, list) or not options:
            raise CanaryCheckError("Completion response contained no choices")
        counts[by_id[deployment]] += 1
    p = weight / 100.
    target = count * p
    tolerance = 0. if weight in (0, 100) else max(4 * math.sqrt(count * p * (1-p)), 0.05 * count)
    ok = abs(counts["canary"] - target) <= tolerance
    return {
        "schema": "modelops.canary.http.v1", "status": "PASS" if ok else "FAIL_DISTRIBUTION",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "public_group": group, "gateway_origin": base,
        "requests": count, "stable": counts["stable"], "canary": counts["canary"],
        "expected_canary_percent": weight,
        "measured_canary_percent": 100 * counts["canary"] / count,
        "allowable_sample_error_count": tolerance,
        "duration_seconds": round(time.monotonic() - first, 3),
        "evidence": "live_http_deployment_id_headers_not_config_template",
        "caveat": "Statistical sampling is not proof of capacity, accuracy, GPU performance or production HA",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--canary-weight", required=True, type=int)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--api-key-env", default="MODEL_OPS_API_KEY")
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        result = verify(a.base_url, os.getenv(a.api_key_env, ""), a.model,
                        a.canary_weight, a.requests)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"],"requests": result["requests"],
                          "canary_percent": result["measured_canary_percent"]}))
        return 0 if result["status"] == "PASS" else 1
    except (CanaryCheckError, OSError) as exc:
        print(f"Canary routing verification blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
