"""Compare local vision models on the same three photographs.

Writes one JSON file per model under vlm/results/.
Uses the Ollama HTTP API on 127.0.0.1:11434. No extra packages.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from prompt_template import RESPONSE_SCHEMA, render_prompt

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
RESULTS = ROOT / "results"
HOST = "http://127.0.0.1:11434"

# Keep the context small so a 6 GB laptop GPU can hold the weights.
OPTIONS = {
    "temperature": 0.2,
    "num_predict": 256,
    "num_ctx": 2048,
}


def load_images() -> list[dict]:
    manifest = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
    loaded = []
    for item in manifest["images"]:
        path = SAMPLES / item["file"]
        loaded.append(
            {
                **item,
                "b64": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        )
    return loaded


def gpu_snapshot() -> str:
    try:
        done = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable ({exc})"
    return (done.stdout or done.stderr).strip()


def post_chat(model: str, prompt: str, image_b64: str, timeout: int) -> dict:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": RESPONSE_SCHEMA,
        "keep_alive": "10m",
        "options": OPTIONS,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
    }
    request = urllib.request.Request(
        f"{HOST}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    payload["_wall_seconds"] = round(time.perf_counter() - started, 3)
    return payload


def score_output(text: str, expected_ids: list[str]) -> dict:
    result = {
        "json_ok": False,
        "only_expected_ids": False,
        "fields_ok": False,
        "ids": [],
        "error": None,
    }
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        result["error"] = f"invalid json: {exc}"
        return result
    result["json_ok"] = True
    rows = parsed.get("criteria")
    if not isinstance(rows, list):
        result["error"] = "criteria is not a list"
        return result
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    result["ids"] = ids
    result["only_expected_ids"] = ids == expected_ids
    fields_ok = True
    for row in rows:
        if not isinstance(row, dict):
            fields_ok = False
            break
        score = row.get("fit_score")
        evidence = row.get("evidence")
        label = row.get("tone_label")
        if not isinstance(score, int) or not 1 <= score <= 5:
            fields_ok = False
        if not isinstance(evidence, str) or len(evidence.strip()) < 12:
            fields_ok = False
        if not isinstance(label, str) or not label.strip():
            fields_ok = False
    result["fields_ok"] = fields_ok and bool(rows)
    return result


def ns_to_s(value) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(value / 1e9, 3)


def run_model(model: str, images: list[dict], timeout: int) -> dict:
    prompt = render_prompt(["B1"])
    rows = []
    print(f"\n=== {model} ===", flush=True)
    for image in images:
        print(f"  {image['file']} ...", flush=True)
        row = {
            "file": image["file"],
            "scene": image["scene"],
        }
        try:
            payload = post_chat(model, prompt, image["b64"], timeout)
        except Exception as exc:  # noqa: BLE001 — record the failure and keep going
            row["error"] = str(exc)
            row["gpu"] = gpu_snapshot()
            rows.append(row)
            print(f"    ERROR {exc}", flush=True)
            continue
        message = payload.get("message") or {}
        content = message.get("content") or ""
        row.update(
            {
                "wall_seconds": payload.get("_wall_seconds"),
                "load_seconds": ns_to_s(payload.get("load_duration")),
                "prompt_eval_seconds": ns_to_s(payload.get("prompt_eval_duration")),
                "eval_seconds": ns_to_s(payload.get("eval_duration")),
                "eval_count": payload.get("eval_count"),
                "gpu": gpu_snapshot(),
                "content": content,
                "thinking": message.get("thinking") or "",
                "checks": score_output(content, ["B1"]),
            }
        )
        eval_count = row["eval_count"] or 0
        eval_seconds = row["eval_seconds"] or 0
        row["tokens_per_second"] = (
            round(eval_count / eval_seconds, 2) if eval_seconds else None
        )
        print(
            f"    wall={row['wall_seconds']}s eval={row['eval_seconds']}s "
            f"tok/s={row['tokens_per_second']} json={row['checks']['json_ok']}",
            flush=True,
        )
        rows.append(row)
    return {
        "model": model,
        "prompt": prompt,
        "options": OPTIONS,
        "think": False,
        "runs": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    images = load_images()
    RESULTS.mkdir(exist_ok=True)
    for model in args.models:
        report = run_model(model, images, args.timeout)
        safe_name = model.replace(":", "_")
        out = RESULTS / f"{safe_name}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
