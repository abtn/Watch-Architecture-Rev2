# ADR-0031 — Initial Cloudflare Workers AI Generation Provider

## Status

**Accepted — initial R6-E generation-provider/model selection, 2026-10-30.** The operator explicitly selected Cloudflare Workers AI with Meta Llama 3.1 8B Instruct FP8 for the first hosted generation integration. This authorizes the bounded R6-E work only; it does not authorize R6-F, R6-G, autonomous learning acceptance, or any change to Kernel authority.

## Decision

Use Cloudflare Workers AI through its OpenAI-compatible Chat Completions endpoint for the first hosted generation provider.

- **Provider:** Cloudflare Workers AI.
- **Adapter identifier:** `cloudflare_workers_ai`.
- **Model:** `@cf/meta/llama-3.1-8b-instruct-fp8`.
- **Model family/size:** Meta Llama 3.1, 8B parameters, FP8.
- **Advertised context window:** 32,000 tokens. Watch's initial retrieval contract remains at most eight passages and 8,000 Unicode characters; the provider's larger context does not expand the Watch context budget.
- **Published unit price (2026-10-30):** $0.152 per million input tokens and $0.287 per million output tokens. Cloudflare bills through Neurons; the pricing page currently lists 13,778 input Neurons and 26,128 output Neurons per million tokens for this model.
- **Endpoint:** `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions`.
- **Base URL configuration:** the account-scoped prefix ending in `/ai/v1`.
- **Authentication:** bearer token created from the Cloudflare Workers AI API-token template. A custom token requires both Workers AI Read and Workers AI Edit permissions.
- **Request behavior:** synchronous, non-streaming, one HTTP request per adapter invocation. The adapter does not retry internally. Transient provider errors are categorized for the ordinary Task retry boundary.
- **Tools:** no tool calling or function calling in the first integration. Model output cannot request arbitrary tools or capabilities.
- **Reasoning:** do not request, expose, log, or persist reasoning/chain-of-thought traces. Retain only a final structured proposal and the minimum provider usage metadata needed for accounting and audit.
- **Structured output:** ask for one JSON object in the prompt and validate it locally with the existing strict Pydantic `StrategyProposal` schema. Do not rely on Cloudflare JSON Mode for the selected FP8 model: the currently published JSON Mode support list does not explicitly list this exact model ID. Do not send an unverified `response_format` configuration.

## Authority and integration boundary

The model is a proposal producer, not an application authority.

1. The provider adapter returns untrusted final JSON plus input/output token usage. It performs no database or Snapshot writes.
2. R6-E Context assembly resolves retrieved candidates to current canonical records, checks Team/source authorization and freshness, and preserves the exact Context Snapshot and Task-attributed manifest required by ADR-0028.
3. The application validates the JSON with `StrategyProposal`, then submits it through the existing `StrategyService` validation and audit path.
4. Only an accepted proposal may be used by the existing Plan materialization path. The provider cannot create Plans/Tasks, alter TeamPolicy, widen Task scope, or commit durable domain state.
5. The Context Snapshot and `context_assembled` Event are narrowly scoped application-managed effects of the current `propose_strategy` Task. They are not worker/model writes. A matching replay reuses the existing immutable Snapshot and manifest; it never replaces them.
6. No second Task runtime, scheduler, or provider-specific decision logic is introduced. The provider is replaceable through the small generation-provider boundary.

The existing R4 Strategy audit remains embedded in the strategy disposition Event and does not acquire a second Snapshot. The new Context Snapshot represents the exact R6-E model input and is a different artifact.

## Usage, cost, and fail-closed requirements

The adapter requires the provider response to include valid `prompt_tokens` and `completion_tokens`; if usage is absent or malformed, it rejects the result. It computes an estimated model cost from the published per-token rates. This estimate is operational metadata, not a billing statement or proof of complete account-wide spend.

The current provider adapter is a stateless API smoke/provider foundation and is not yet a Task execution path. **Before any provider call is wired into a production `propose_strategy` Task**, R6-E must add Task-attributed cost reservation and reconciliation using the Task's `max_cost_usd` budget. It must reserve a conservative maximum before the request, reconcile the reservation against returned usage afterwards, and fail closed if actual usage cannot be established. A request with unknown usage cannot yield an accepted Strategy. This does not claim that Watch currently has complete token-spend accounting.

The first Task integration must use a bounded input/output budget compatible with the Watch Context limits and the model's 32K maximum. The initial maximum output is 1,024 tokens. No hidden provider retry is allowed; retries, when safe and budgeted, occur only as ordinary Task attempts through TaskRuntime. Preserve the existing three-start Task limit.

Cloudflare Workers AI currently includes 10,000 Neurons per day at no charge, resetting at 00:00 UTC. On Workers Free, additional requests fail after the daily allocation. Workers Paid charges $0.011 per 1,000 Neurons above the included allocation. Neurons measure model compute; 10,000 Neurons is not a fixed token allowance.

## Data handling

Cloudflare states that standard stateless Workers AI inference requests are processed only as needed to return the response, with zero retention afterwards, and that Customer Content is not used to train AI models. Operational metadata may still be retained for service operation, security, support, and billing. Stateful features, customer-directed storage, AI Gateway logging/caching, R2/KV/Vectorize integration, or application logs can retain content under their own lifecycle rules. The initial Watch adapter uses stateless synchronous inference, does not use AI Gateway, and must not log request/response bodies or credentials. Review Cloudflare's current data-usage terms before sending sensitive or regulated material.

## Alternatives and deferrals

- **Llama 4 Scout 17B:** not selected for the first integration. Its published per-token price is higher and its vision/extended-context capabilities are not needed for the first text-only StrategyProposer.
- **Qwen 3.8 27B:** retained as a quality benchmark, not the initial production model, because its current hosted token price is materially higher.
- **Local LM Studio Qwen 3.8 4B Distill:** remains a local fallback and comparison baseline; it does not replace the hosted provider decision.
- Additional providers/models, automatic model routing, provider-side tools, model failover, streaming, and R6-F distillation use are deferred.

## References

- [Cloudflare Llama 3.1 8B Instruct FP8 model](https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct-fp8/)
- [Workers AI OpenAI-compatible API](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Workers AI data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/)
- [Workers AI JSON Mode and supported models](https://developers.cloudflare.com/workers-ai/features/json-mode/)
- [Cloudflare REST API token verification](https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/)
