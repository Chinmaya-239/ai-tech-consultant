import type { ZodType, ZodTypeDef } from "zod";

/** LLM_PROVIDER=anthropic (default, Claude) or openai_compat (Groq, Gemini, Ollama, OpenRouter...). Only askJson is used by the app. */
const PROVIDER = process.env.LLM_PROVIDER ?? "anthropic";
export const FAST = PROVIDER === "openai_compat" ? (process.env.LLM_FAST_MODEL ?? "") : (process.env.CLAUDE_FAST ?? "claude-haiku-5-5");
export const SMART = PROVIDER === "openai_compat" ? (process.env.LLM_SMART_MODEL ?? "") : (process.env.CLAUDE_SMART ?? "claude-sonnet-5-5");
export const usage: { model: string; in: number; out: number; ms: number }[] = [];
let anthropic: any = null;

async function complete(model: string, system: string, user: string): Promise<string> {
  const t0 = Date.now();
  if (PROVIDER === "openai_compat") {
    for (let a = 0; a < 5; a++) {                       // free tiers rate-limit: back off and retry
      const r = await fetch(`${(process.env.LLM_BASE_URL ?? "").replace(/\/$/, "")}/chat/completions`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.LLM_API_KEY ?? ""}` },
        body: JSON.stringify({ model, max_tokens: process.env.LLM_REASONING_EFFORT ? 4500 : 1500, temperature: 0, ...(process.env.LLM_REASONING_EFFORT ? { reasoning_effort: process.env.LLM_REASONING_EFFORT } : {}), messages: [{ role: "system", content: system }, { role: "user", content: user }] }),
        signal: AbortSignal.timeout(120_000) });
      if (r.status === 429 || r.status >= 500) { await new Promise((s) => setTimeout(s, Math.min(Number(r.headers.get("retry-after") ?? 2 ** a * 2), 30) * 1000)); continue; }
      if (!r.ok) throw new Error(`LLM HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
      const d = (await r.json()) as { choices: { message: { content: string | null } }[]; usage?: { prompt_tokens?: number; completion_tokens?: number } };
      usage.push({ model, in: d.usage?.prompt_tokens ?? 0, out: d.usage?.completion_tokens ?? 0, ms: Date.now() - t0 });
      return d.choices[0]?.message.content ?? "";
    }
    throw new Error("LLM provider kept rate-limiting or failing");
  }
  if (!anthropic) { const { default: A } = await import("@anthropic-ai/sdk"); anthropic = new A(); }
  const r = await anthropic.messages.create({ model, max_tokens: 1500, system, messages: [{ role: "user", content: user }] });
  usage.push({ model, in: r.usage.input_tokens, out: r.usage.output_tokens, ms: Date.now() - t0 });
  return r.content.map((b: { type: string; text?: string }) => (b.type === "text" ? b.text : "")).join("");
}

function extractJson(text: string): unknown {
  const t = text.replace(/^```(?:json)?|```$/gm, "").trim();
  try { return JSON.parse(t); } catch { const a = t.indexOf("{"), b = t.lastIndexOf("}"); if (a >= 0 && b > a) return JSON.parse(t.slice(a, b + 1)); throw new Error("no JSON found"); }
}

export async function askJson<T>(model: string, system: string, user: string, schema: ZodType<T, ZodTypeDef, unknown>, retries = 2): Promise<T> {
  let prompt = user; let lastErr = "";
  for (let i = 0; i <= retries; i++) {
    const text = await complete(model, system + "\nReturn ONLY valid JSON, no markdown, no commentary.", prompt);
    try { return schema.parse(extractJson(text)); }        // schema-validated, retried on failure
    catch (e) { lastErr = String(e); prompt = `${user}\n\nYour previous reply failed validation: ${lastErr.slice(0, 300)}. Fix it.`; }
  }
  throw new Error(`LLM output failed schema validation: ${lastErr.slice(0, 200)}`);
}
