# Research notes (sourced, read Nov 6, 2026)

## Tavily API
- Search (POST /search). Key options: `search_depth` basic, fast, ultra-fast (1 credit) or advanced (2 credits);
  `max_results` 0 to 20, default 10; `topic` general, news or finance; `time_range`, `start_date`, `end_date`;
  `include_domains` (up to 300) with `include_domains_mode` restrict or prefer; `exclude_domains` (up to 150);
  `include_raw_content`; `include_usage`; `exact_match`; `auto_parameters` (can silently switch to advanced, so
  set depth explicitly). Response results carry title, url, content, score, raw_content, published_date, id.
  Auth header: `Authorization: Bearer tvly-...`.
  Source: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Extract (POST /extract): 1 to 20 URLs; optional `query` reranks chunks; `chunks_per_source` 1 to 5;
  `extract_depth` basic or advanced (tables); `format` markdown or text; `timeout`; `include_usage`. Cost: basic 1
  credit per 5 successful URLs, advanced 2 per 5; failed URLs free. Check both `results` and `failed_results`.
  Source: https://docs.tavily.com/documentation/api-reference/endpoint/extract
- Pricing: free plan 1,000 credits a month, no card; pay as you go $0.008 per credit.
  Source: https://www.tavily.com/pricing
- Event code (attendee packet): HACK1984 gives 8,000 credits, valid Nov 6 to 9, limited.
- Tavily does not keep its own index; it fans out to multiple sources and engines in real time.
  Source: https://sacra.com/c/tavily/
- Nebius agreed to acquire Tavily in February 2026 for $275 million. Source: https://sacra.com/c/tavily/

## Competitors
- Pipelock (PipeLab, open source core): content and payload inspection, credential DLP with multi-layer decoding,
  injection detection in responses, hash-chained flight recorder, signed action receipts. Note: the source is
  PipeLab's own blog. https://pipelab.org/blog/best-ai-agent-security-tools-2026/
- Docker MCP Gateway (secret-shaped data blocking), Runlayer, agentgateway, Cisco mcp-scanner, Snyk agent-scan
  (formerly Invariant Labs). Same source.
- mcp-firewall (open source): policy engine, egress control, audit logging. https://github.com/ressl/mcp-firewall
- PointGuard AI MCP Security Gateway with DLP. https://www.pointguardai.com/mcp-security-gateway
- Snowflake Cortex AI Gateway and Data Exfiltration Prevention (Black Hat, July 2026).
  https://www.snowflake.com/en/blog/enterprise-ai-security-agentic-mcp-governance/

## Prior art
- Willison, "The lethal trifecta for AI agents" (June 16, 2025): private data, untrusted content, external
  communication. Says 95% detection is a failing grade; lists incidents including Microsoft 365 Copilot, GitHub's
  MCP server, GitLab Duo. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- CaMeL: Debenedetti et al., "Defeating Prompt Injections by Design", Google DeepMind, arXiv 2503.18813 (March
  2025). Privileged LLM plans; quarantined LLM handles untrusted data without tools. https://arxiv.org/abs/2503.18813
- Beurer-Kellner et al., "Design Patterns for Securing LLM Agents against Prompt Injections" (June 2025): six
  patterns including Dual LLM and Plan-Then-Execute. https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/

## Claude Code's own sandbox (context for the pitch)
The sandbox's network proxy allows traffic by requested hostname and does not inspect TLS, so it does not check
what is inside an allowed request. https://www.penligent.ai/hackinglabs/ko/?p=5317

## Local models for the Planner
Reviews this year rank Qwen3 8B (about 8 GB at Q4) as a good default for tool calling on Ollama; larger models
need far more memory. These are blog rankings, not audited numbers: test two models on the Planner's job and keep
the one that follows the schema. The Planner does not need tool calling if it returns JSON for the gate;
structured output is enough.

Measured on Nov 7 (team):
- Ollama /api/chat needs `"think": false` in the request body and the JSON schema in `"format"`. `/no_think` in the
  prompt does not work: about 2 minutes per call vs 3 seconds.
- Put today's date in the Planner prompt; qwen3 otherwise assumes it is 2024.
- Model from `.env` `OLLAMA_MODEL`: `qwen3:4b` for development, `qwen3:8b` on the demo laptop.
- Red-team and false-block numbers are measured on `qwen3:8b`.

## Fictional names check
"Fenwick" is a real law firm (Fenwick & West) active in fintech: do not use. "Brackwater Payments" and "Ossory
Capital" returned no exact matches on Nov 6.
