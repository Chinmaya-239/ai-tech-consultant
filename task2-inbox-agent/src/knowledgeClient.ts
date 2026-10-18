import type { KbResult } from "./types.js";
const KB_URL = process.env.KB_URL ?? "http://localhost:8001";
const KB_KEY = process.env.KB_API_KEY ?? "dev-key";

/** Typed client for Task 1's HTTP API. Never throws; never invents an answer when the service fails. */
export async function askKnowledge(question: string, requestId: string, timeoutMs = 45_000): Promise<KbResult> {
  try {
    const r = await fetch(`${KB_URL}/query`, { method: "POST", headers: { "Content-Type": "application/json", "X-API-Key": KB_KEY },
      body: JSON.stringify({ question, request_id: requestId }), signal: AbortSignal.timeout(timeoutMs) });
    if (!r.ok) return { status: "kb_unavailable", error: `HTTP ${r.status}` };
    const d = (await r.json()) as { status: string; answer: string | null; sources: { title: string; url: string }[]; uncertainty?: string | null; escalation_id?: number | null };
    if (d.status === "answered" && d.answer) return { status: "answered", answer: d.answer, sources: d.sources, uncertainty: d.uncertainty ?? null };
    return { status: "insufficient_evidence", escalation_id: d.escalation_id ?? null };
  } catch (e) { return { status: "kb_unavailable", error: String(e) }; }
}
