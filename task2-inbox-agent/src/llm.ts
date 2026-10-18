import Anthropic from "@anthropic-ai/sdk";
import type { ZodType, ZodTypeDef } from "zod";

export const FAST = process.env.CLAUDE_FAST ?? "claude-haiku-5-5";
export const SMART = process.env.CLAUDE_SMART ?? "claude-sonnet-5-5";
export const usage: { model: string; in: number; out: number; ms: number }[] = [];
let client: Anthropic | null = null;

export async function askJson<T>(model: string, system: string, user: string, schema: ZodType<T, ZodTypeDef, unknown>, retries = 2): Promise<T> {
  client ??= new Anthropic();
  let prompt = user; let lastErr = "";
  for (let i = 0; i <= retries; i++) {
    const t0 = Date.now();
    const r = await client.messages.create({ model, max_tokens: 1500, system: system + "\nReturn ONLY valid JSON, no markdown.", messages: [{ role: "user", content: prompt }] });
    usage.push({ model, in: r.usage.input_tokens, out: r.usage.output_tokens, ms: Date.now() - t0 });
    const text = r.content.map((b) => (b.type === "text" ? b.text : "")).join("").replace(/^```(?:json)?|```$/gm, "").trim();
    try { return schema.parse(JSON.parse(text)); }          // schema-validated, retried on failure
    catch (e) { lastErr = String(e); prompt = `${user}\n\nYour previous reply failed validation: ${lastErr.slice(0, 300)}. Fix it.`; }
  }
  throw new Error(`LLM output failed schema validation: ${lastErr.slice(0, 200)}`);
}
