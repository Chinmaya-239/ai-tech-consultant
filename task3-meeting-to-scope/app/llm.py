"""LLM layer. LLM_PROVIDER=anthropic (default, Claude) or openai_compat (any OpenAI-compatible API: Groq, Gemini, Ollama, OpenRouter...).
Everything else in the app calls only ask / ask_json / describe_image, so switching provider is an .env change."""
import os, json, re, time
import httpx

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
if PROVIDER == "openai_compat":
    FAST = os.getenv("LLM_FAST_MODEL", "")
    SMART = os.getenv("LLM_SMART_MODEL", "")
    BASE = os.getenv("LLM_BASE_URL", "").rstrip("/")
    KEY = os.getenv("LLM_API_KEY", "")
else:
    FAST = os.getenv("CLAUDE_FAST", "claude-haiku-5-5")
    SMART = os.getenv("CLAUDE_SMART", "claude-sonnet-5-5")
_c = None
USAGE: list[dict] = []   # per-call usage, used by evals for cost/latency

def client():
    global _c
    if _c is None:
        import anthropic
        _c = anthropic.Anthropic()
    return _c

def _compat(model: str, system: str, user: str, max_tokens: int) -> str:
    t0 = time.time()
    for attempt in range(5):                      # free tiers rate-limit: back off and retry
        r = httpx.post(f"{BASE}/chat/completions", timeout=120,
                       headers={"Authorization": f"Bearer {KEY}"},
                       json={"model": model, "max_tokens": max_tokens * (3 if os.getenv("LLM_REASONING_EFFORT") else 1), "temperature": 0, **({"reasoning_effort": os.getenv("LLM_REASONING_EFFORT")} if os.getenv("LLM_REASONING_EFFORT") else {}),
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(float(r.headers.get("retry-after", 2 ** attempt * 2)), 30)); continue
        r.raise_for_status()
        d = r.json(); u = d.get("usage", {})
        USAGE.append({"model": model, "in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0), "ms": int((time.time() - t0) * 1000)})
        return d["choices"][0]["message"]["content"] or ""
    raise RuntimeError("LLM provider kept rate-limiting or failing")

def ask(system: str, user, model: str | None = None, max_tokens: int = 1200) -> str:
    model = model or SMART
    if PROVIDER == "openai_compat":
        return _compat(model, system, user, max_tokens)
    t0 = time.time()
    r = client().messages.create(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    USAGE.append({"model": model, "in": r.usage.input_tokens, "out": r.usage.output_tokens, "ms": int((time.time() - t0) * 1000)})
    return "".join(b.text for b in r.content if b.type == "text")

def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")            # small models often add prose around the JSON
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise

def ask_json(system: str, user, model: str | None = None, max_tokens: int = 1500, retries: int = 2) -> dict:
    last = ""
    for _ in range(retries + 1):
        last = ask(system + "\nReturn ONLY valid JSON, no markdown fences, no commentary.", user, model, max_tokens)
        try:
            return parse_json(last)
        except json.JSONDecodeError:
            user = f"{user}\n\n(Previous reply was not valid JSON. Reply with JSON only.)"
    raise ValueError(f"model did not return JSON: {last[:200]}")
