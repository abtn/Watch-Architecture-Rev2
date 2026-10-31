# Cloudflare Workers AI — Initial Generation Provider

This guide configures the first R6-E hosted generation provider selected in [ADR-0031](../decisions/ADR-0031-cloudflare-workers-ai-generation.md).

## Selected model and endpoint

- Provider: `cloudflare_workers_ai`
- Model: `@cf/meta/llama-3.1-8b-instruct-fp8`
- Advertised context: 32,000 tokens
- Chat Completions endpoint: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions`
- Base URL: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`
- Protocol: OpenAI-compatible Chat Completions, synchronous and non-streaming.

The account identifier in an R2 endpoint such as `https://<account-id>.r2.cloudflarestorage.com` is the account ID, but that R2 hostname is **not** the Workers AI API hostname. Do not configure the R2 endpoint as `WATCH_GENERATION_BASE_URL`. The R2 endpoint is not used by this generation adapter.

## Create and verify an API token

In the Cloudflare dashboard, open Workers AI → Use REST API → Create a Workers AI API Token. Prefer the prefilled Workers AI token template. A manually created token needs both account-scoped `Workers AI Read` and `Workers AI Edit` permissions. Limit the token to the intended account, keep an expiry where practical, and store the secret in a password manager or local secret manager.

For the account-specific token verification endpoint, Cloudflare documents:

```powershell
$ErrorActionPreference = "Stop"

$accountId = "ebe192e5f12ef9179256494d640201c6"
if (-not $env:WATCH_GENERATION_API_KEY) {
    throw "Set WATCH_GENERATION_API_KEY before verifying the token."
}

$headers = @{
    Authorization = "Bearer $env:WATCH_GENERATION_API_KEY"
}
$verifyUrl = "https://api.cloudflare.com/client/v4/accounts/$accountId/tokens/verify"
$verify = Invoke-RestMethod -Method Get -Uri $verifyUrl -Headers $headers

if (-not $verify.success -or $verify.result.status -ne "active") {
    throw "Cloudflare API token is not active."
}
$verify.result | Select-Object id, status, expires_on
```

Do not paste the token into chat, a prompt, a source file, a terminal command literal, or a Git-tracked `.env` file. The verification response should report `status = active`.

## Configure the current PowerShell session

The account ID below was supplied in the operator's R2 endpoint. It is an account identifier, not an API secret.

```powershell
$ErrorActionPreference = "Stop"

$env:WATCH_GENERATION_PROVIDER = "cloudflare_workers_ai"
$env:WATCH_GENERATION_BASE_URL = "https://api.cloudflare.com/client/v4/accounts/ebe192e5f12ef9179256494d640201c6/ai/v1"
$env:WATCH_GENERATION_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8"
$env:WATCH_GENERATION_TIMEOUT_SECONDS = "60"
$env:WATCH_GENERATION_MAX_OUTPUT_TOKENS = "1024"

# Paste the token interactively. Do not echo it or add it to Git.
$secureToken = Read-Host "Cloudflare Workers AI API token" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $env:WATCH_GENERATION_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
}
```

These variables last only for the current PowerShell process tree. Do not add them to project files. Clear the key when finished:

```powershell
Remove-Item Env:WATCH_GENERATION_API_KEY -ErrorAction SilentlyContinue
```

## Run the real-provider smoke test

After syncing the branch and installing the project environment, run:

```powershell
uv run python -m core.generation_smoke
```

This makes one real, stateless Chat Completions request. It does not connect to PostgreSQL, create a Task, persist a Context Snapshot, or write application state. A passing result confirms the configured endpoint, token, model access, final JSON parsing, and provider token-usage response. It prints token counts, an estimated per-request cost, elapsed time, request ID, and the tiny smoke response. It does not print the API key, prompts, or any reasoning trace.

The adapter sends `stream: false`, asks for JSON in the system prompt, and validates the response as a JSON object locally. Cloudflare's published JSON Mode supported-model list does not explicitly include the exact FP8 model ID selected here, so this adapter deliberately does not send `response_format`. The real StrategyProposer must additionally validate the object against the existing strict Pydantic `StrategyProposal` schema.

## Price and free allocation

Cloudflare's pricing page last updated 2026-10-20 lists this model at:

| Token type | Price |
|---|---:|
| Input | $0.152 / million tokens |
| Output | $0.287 / million tokens |

The corresponding published neuron rates are 13,778 input Neurons and 26,128 output Neurons per million tokens. Workers AI includes 10,000 Neurons per day at no charge, resetting at 00:00 UTC. On Workers Free, requests fail after the daily allocation is exceeded. On Workers Paid, additional usage is billed at $0.011 per 1,000 Neurons. Neurons are compute units; the daily free allowance is not a fixed number of tokens. Monitor actual Neuron consumption in the Cloudflare dashboard.

The adapter reports an estimated cost computed from returned `prompt_tokens` and `completion_tokens` using the published prices. Pricing can change; treat the estimate as a diagnostic, not an invoice or complete account-spend ledger.

## Data handling and logging

Cloudflare states that standard stateless Workers AI inference requests are retained only as needed to provide the service and are not used to train models. Cloudflare may retain operational metadata such as model/account identifiers, timestamps, token/Neuron counts, latency, and normalized status/error codes. Logging/caching in AI Gateway, writing content to application logs, or using R2/KV/Vectorize and other stateful features may retain Customer Content under those features' terms and retention controls.

The initial adapter uses the stateless Workers AI endpoint directly. Do not enable AI Gateway request/response logging or caching for this initial integration. Never log credentials, prompt bodies, full model responses, or reasoning traces. The application will preserve only validated structured proposals and their required evidence/provenance through Watch's existing Task and Snapshot rules.

## Task integration is a separate R6-E step

The smoke command is a provider connectivity test, not a production Task execution path. The bounded Context assembler, Context Snapshot/manifest, Context-bound StrategyProposer, application validation, and Task-attributed generation cost reservation/reconciliation are implemented as separate R6-E checkpoints. The proposer remains outside automatic Task dispatch; production invocation through a dispatcher is not enabled by this provider-only guide. If token usage is missing or malformed, the model response must not be accepted. Do not claim complete global spend accounting from this initial adapter.


## Task-attributed generation cost accounting

The Task proposer does not call the provider directly until a durable cost
reservation has committed. The provider quotes a conservative maximum for the
exact prompt and configured output cap using the pinned ADR-0031 rate card.
The initial implementation bounds input tokens by UTF-8 prompt bytes plus 128
message-framing tokens; input plus output must fit the model's 32K context
window and output is capped at 1,024 tokens.

A unique `task_generation_charges` row is written per Task attempt and
`strategy_proposal` operation before the network request. Reservation checks
the Task-wide `max_cost_usd` ceiling while holding the Task row lock and
includes all prior reconciled and unresolved charges. A valid response is
reconciled from provider-reported input/output tokens using the rate card
persisted with that reservation. The usage-derived amount is an estimate, not
Cloudflare's final account invoice.

A provider failure, missing/malformed usage, or ambiguous reconciliation
leaves the maximum reservation in an `unknown` state. It is not released.
An over-bound response is recorded as `overrun`, accounted at no less than
the reserved amount, and cannot produce a Strategy disposition. A retry can
make a new request only on a later TaskRuntime attempt and only if its new
reservation fits on top of all previous Task charges. The same attempt cannot
invoke the provider twice.
