"""Run one real, stateless Cloudflare Workers AI generation smoke request.

Configure WATCH_GENERATION_* in the current shell first. This command does not
connect to PostgreSQL, create a Task, persist a Snapshot, or store a transcript.
"""

from __future__ import annotations

import json
import sys

from . import generation


_SYSTEM_PROMPT = (
    "You are a strict JSON-only assistant. Return one JSON object and no "
    "markdown fences or commentary. Do not include hidden reasoning."
)
_USER_PROMPT = (
    "Return exactly this shape: "
    '{"status":"ok","summary":"one short sentence"}. '
    "Set status to ok and make the summary describe a successful API smoke test."
)


def main() -> int:
    try:
        provider = generation.CloudflareWorkersAIGenerationProvider.from_environment()
        result = provider.generate_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_USER_PROMPT,
            temperature=0.0,
        )
    except (ValueError, generation.GenerationProviderError) as error:
        print(f"Generation smoke FAILED: {error}", file=sys.stderr)
        return 1

    if result.content.get("status") != "ok":
        print("Generation smoke FAILED: unexpected JSON result", file=sys.stderr)
        return 1
    summary = result.content.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        print("Generation smoke FAILED: missing summary", file=sys.stderr)
        return 1

    report = {
        "status": "PASS",
        "provider": "cloudflare_workers_ai",
        "model": result.model,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "estimated_cost_usd": str(result.usage.estimated_cost_usd),
        "elapsed_seconds": round(result.elapsed_seconds, 3),
        "request_id": result.request_id,
        "response": result.content,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
