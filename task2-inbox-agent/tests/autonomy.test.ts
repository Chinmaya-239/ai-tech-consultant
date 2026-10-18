import { describe, it, expect } from "vitest";
import { recordOutcome, enableCategory, unchanged, canAutoSend, type AutonomyState } from "../src/autonomy.js";
import { policyFlags } from "../src/policy.js";
import type { Interaction } from "../src/types.js";

const mk = (cat: Interaction["classification"]["category"], risk: "low" | "high" = "low"): Interaction => ({
  id: Math.random().toString(), email: { from: "a@b.c", subject: "s", body: "b" }, kb: null, policyFlags: [], promptVersion: "t", models: { fast: "f", smart: "s" },
  classification: { category: cat, urgency: "normal", risk, summary: "x", needs_knowledge: true, knowledge_question: "q", suspicious_instructions: false },
  draft: { reply: "Hello there, here is how.", sources: ["https://x"], risk: "low", needs_human: false, next_action: null, follow_up_date: null }, state: "pending_review", created: "" });

describe("20-consecutive rule", () => {
  it("becomes eligible after 20 unchanged, resets on one edit", () => {
    let s: AutonomyState = {}; for (let n = 0; n < 19; n++) s = recordOutcome(s, mk("how_to"), true);
    expect(s.how_to?.eligible).toBe(false); s = recordOutcome(s, mk("how_to"), false); expect(s.how_to?.streak).toBe(0);
    for (let n = 0; n < 20; n++) s = recordOutcome(s, mk("how_to"), true); expect(s.how_to?.eligible).toBe(true);
  });
  it("eligibility is not permission; enabling is explicit, and an edit demotes", () => {
    let s: AutonomyState = {}; for (let n = 0; n < 20; n++) s = recordOutcome(s, mk("how_to"), true);
    expect(canAutoSend(s, mk("how_to"))).toBe(false);
    s = enableCategory(s, "how_to"); expect(canAutoSend(s, mk("how_to"))).toBe(true);
    s = recordOutcome(s, mk("how_to"), false); expect(s.how_to?.enabled).toBe(false);
  });
  it("refunds/complaints never qualify or enable", () => {
    let s: AutonomyState = {}; for (let n = 0; n < 25; n++) s = recordOutcome(s, mk("refund_cancellation"), true);
    expect(s.refund_cancellation?.eligible).toBe(false); expect(() => enableCategory(s, "refund_cancellation")).toThrow();
  });
  it("compares text, not clicks", () => { expect(unchanged("Hi  there\n", "Hi there")).toBe(true); expect(unchanged("Hi there", "Hi there!")).toBe(false); });
  it("policy guard catches commitments", () => {
    expect(policyFlags("We will refund you today.")).toContain("promises refund/credit");
    expect(policyFlags("It costs $200.")).toContain("contains a price"); expect(policyFlags("Open Settings > Design.")).toEqual([]);
  });
});
