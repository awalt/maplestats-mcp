### Changed

- The chat demo's step budget is cut from 12 to 2 requests per question (`CHAT_MAX_TOOL_STEPS`,
  still set by environment variable). On the Anthropic path one request is not one model call:
  the MCP connector runs up to about 10 model steps inside it before it pauses the turn, so 12
  requests allowed about 120 steps for one question (a vague question made 17 tool calls over
  93 to 158 s) and 2 allow about 20. The second request is the last, and its system prompt now
  tells the model to stop calling tools and answer with what it has and say what is missing; if
  it still pauses or writes nothing, the visitor gets the step-limit message as before. The
  first request's prompt gains one sentence asking the model to put independent calls in the
  same step. The `openai` backend, where the app runs the loop and a round is one model call,
  has its own limit, `CHAT_MAX_TOOL_ROUNDS`, which keeps the old default of 12 (at most 12
  model steps); its last round gets the same wrap-up, and a tool call asked for in it is not
  run.
- The chat demo can turn on prompt caching with `CHAT_PROMPT_CACHE=1` (off by default, so the
  request is unchanged until it is set): the system prompt and the MCP toolset carry
  `cache_control: {"type": "ephemeral"}`, which caches the tool list and the prompt (about
  1,800 tokens, above Haiku 5.5's 512-token minimum). Cache reads and writes show as
  `cache_read` and `cache_write` under `tokens` in the chat's `/stats`, as before.
- The chat's `/stats` gains `per_answer`: for each answered question, how many requests to the
  model, tool calls and model steps it took, as p50, p95 and a histogram, also per UTC day
  under `by_day`. Counts only, like the rest of `/stats`: never a question, an answer, a tool's
  arguments or an address.
