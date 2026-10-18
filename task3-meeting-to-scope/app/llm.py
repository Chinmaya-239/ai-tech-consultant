import os, json, re, time
import anthropic
FAST = os.getenv("CLAUDE_FAST", "claude-haiku-5-5")
SMART = os.getenv("CLAUDE_SMART", "claude-sonnet-5-5")
_c = None
USAGE: list[dict] = []   # per-call usage, used by evals for cost/latency

def client() -> anthropic.Anthropic:
    global _c
    if _c is None:
        _c = anthropic.Anthropic()
    return _c

def _log(model, resp, t0):
    USAGE.append({"model": model, "in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
                  "ms": int((time.time() - t0) * 1000)})

def ask(system: str, user, model: str | None = None, max_tokens: int = 1200) -> str:
    model = model or SMART
    t0 = time.time()
    r = client().messages.create(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    _log(model, r, t0)
    return "".join(b.text for b in r.content if b.type == "text")

def ask_json(system: str, user, model: str | None = None, max_tokens: int = 1500, retries: int = 2) -> dict:
    last = ""
    for _ in range(retries + 1):
        last = ask(system + "\nReturn ONLY valid JSON, no markdown fences.", user, model, max_tokens)
        try:
            return json.loads(re.sub(r"^```(?:json)?|```$", "", last.strip(), flags=re.M).strip())
        except json.JSONDecodeError:
            user = f"{user}\n\n(Previous reply was not valid JSON. Reply with JSON only.)"
    raise ValueError(f"model did not return JSON: {last[:200]}")
