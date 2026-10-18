/** Deterministic guard that runs AFTER the model: catches commitments the LLM was told never to make. */
const RULES: [RegExp, string][] = [
  [/\b(we('| wi)ll|i('| wi)ll|you('| wi)ll)\s+(refund|credit|reimburse)/i, "promises refund/credit"],
  [/\brefund(ed)?\b.*\b(approved|processed|issued)\b/i, "states refund approved"],
  [/[$€£₹]\s?\d|\b\d+\s?(usd|dollars|inr|rupees)\b/i, "contains a price"],
  [/\b(guarantee|guaranteed|definitely by|will be (done|live|ready) by)\b/i, "guarantee / delivery date"],
  [/\b(free of charge|no extra cost|at no cost)\b/i, "free-of-charge commitment"],
];
export function policyFlags(text: string): string[] { return RULES.filter(([re]) => re.test(text)).map(([, n]) => n); }
