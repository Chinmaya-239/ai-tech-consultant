import { z } from "zod";

export const CATEGORIES = ["how_to", "troubleshooting", "project_request", "refund_cancellation", "complaint", "quote_request", "follow_up"] as const;
export type Category = (typeof CATEGORIES)[number];
/** Never eligible for autonomous sending, no matter how many unedited drafts accumulate. */
export const ALWAYS_HUMAN: ReadonlySet<Category> = new Set(["refund_cancellation", "complaint", "quote_request", "project_request"]);

export const Classification = z.object({
  category: z.enum(CATEGORIES),
  urgency: z.enum(["low", "normal", "high"]),
  risk: z.enum(["low", "medium", "high"]),
  summary: z.string().min(3),
  needs_knowledge: z.boolean(),
  knowledge_question: z.string().nullable(),
  suspicious_instructions: z.boolean(),
});
export type Classification = z.infer<typeof Classification>;

export const Draft = z.object({
  reply: z.string().min(10),
  sources: z.array(z.string()).default([]),
  risk: z.enum(["low", "medium", "high"]),
  needs_human: z.boolean(),
  next_action: z.string().nullable(),
  follow_up_date: z.string().nullable(),
});
export type Draft = z.infer<typeof Draft>;

export type KbResult =
  | { status: "answered"; answer: string; sources: { title: string; url: string }[]; uncertainty: string | null }
  | { status: "insufficient_evidence"; escalation_id: number | null }
  | { status: "kb_unavailable"; error: string };

export interface Interaction {
  id: string; email: { from: string; subject: string; body: string }; classification: Classification;
  kb: KbResult | null; draft: Draft | null; policyFlags: string[]; promptVersion: string; models: { fast: string; smart: string };
  state: "pending_review" | "sent" | "rejected" | "kb_unavailable" | "needs_expert";
  final?: string; decision?: "approved_unchanged" | "approved_edited" | "rejected" | "auto_sent"; editReason?: string; created: string;
}
