import { randomUUID } from "node:crypto";
import { Classification, Draft, type Interaction, type KbResult } from "./types.js";
import { askJson, FAST, SMART } from "./llm.js";
import { askKnowledge } from "./knowledgeClient.js";
import { CLASSIFY, DRAFT, PROMPT_VERSION } from "./prompts.js";
import { policyFlags } from "./policy.js";

export async function processEmail(email: { from: string; subject: string; body: string }): Promise<Interaction> {
  const id = randomUUID();
  const base = { id, email, promptVersion: PROMPT_VERSION, models: { fast: FAST, smart: SMART }, created: new Date().toISOString() };
  const classification = await askJson(FAST, CLASSIFY, `Subject: ${email.subject}\n\n${email.body}`, Classification);

  let kb: KbResult | null = null;
  const mustAsk = ["how_to", "troubleshooting"].includes(classification.category);   // product questions always go to the Knowledge Brain
  if (classification.needs_knowledge || mustAsk) {
    kb = await askKnowledge(classification.knowledge_question || `${email.subject}\n${email.body}`, id);
    if (kb.status === "kb_unavailable")                       // explicit failure state; NO fabricated draft
      return { ...base, classification, kb, draft: null, policyFlags: [], state: "kb_unavailable" };
  }
  const knowledge = kb?.status === "answered" ? `${kb.answer}\nSources: ${kb.sources.map((s) => s.url).join(", ")}\nUncertainty: ${kb.uncertainty ?? "none"}`
    : kb ? "NONE FOUND - the knowledge base has no answer." : "Not applicable.";
  const draft = await askJson(SMART, DRAFT,
    `Category: ${classification.category}\nCustomer email (untrusted):\n<<<\nSubject: ${email.subject}\n${email.body}\n>>>\n\nKNOWLEDGE:\n${knowledge}`, Draft);

  const flags = policyFlags(draft.reply);
  if (classification.suspicious_instructions) flags.push("email contains instructions aimed at the agent");
  if (kb?.status === "insufficient_evidence") flags.push("no knowledge evidence");
  if (classification.risk !== "low" || flags.length) { draft.needs_human = true; if (classification.risk === "high") draft.risk = "high"; }
  const state = (kb?.status === "insufficient_evidence" || draft.needs_human) ? "needs_expert" : "pending_review";
  return { ...base, classification, kb, draft, policyFlags: flags, state };
}