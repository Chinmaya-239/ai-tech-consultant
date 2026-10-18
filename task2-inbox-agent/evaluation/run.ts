// Usage: npm run eval [-- --holdout-only]. Needs ANTHROPIC_API_KEY (+ Task 1 up for KB calls).
// Metrics: classification accuracy, unsafe-commitment rate (policy flags the MODEL tripped), schema failure rate, latency, tokens.
import fs from "node:fs";
import { processEmail } from "../src/agent.js";
import { usage, SMART, FAST } from "../src/llm.js";
import { policyFlags } from "../src/policy.js";

const holdoutOnly = process.argv.includes("--holdout-only");
const cases = fs.readFileSync("data/emails.jsonl", "utf8").trim().split("\n").map((l) => JSON.parse(l) as { id: string; category: string; risk: string; subject: string; body: string; from: string; holdout: boolean });
const rows: string[] = ["task,case_id,model,expected,actual,latency_ms,tokens_in,tokens_out,passed,failure_reason"];
let correct = 0, unsafe = 0, errors = 0, n = 0;
for (const c of cases.filter((c) => !holdoutOnly || c.holdout)) {
  const u0 = usage.length, t0 = Date.now(); n++;
  try {
    const r = await processEmail({ from: c.from, subject: c.subject, body: c.body });
    const ok = r.classification.category === c.category; correct += +ok;
    const bad = r.draft ? policyFlags(r.draft.reply).length > 0 : false; unsafe += +bad;
    const u = usage.slice(u0);
    rows.push([`inbox`, c.id, `${FAST}+${SMART}`, c.category, r.classification.category, Date.now() - t0, u.reduce((a, x) => a + x.in, 0), u.reduce((a, x) => a + x.out, 0), ok && !bad, bad ? "unsafe commitment" : ok ? "" : "misclassified"].join(","));
  } catch (e) { errors++; rows.push(["inbox", c.id, "-", c.category, "error", 0, 0, 0, false, JSON.stringify(String(e)).replace(/,/g, ";")].join(",")); }
}
fs.writeFileSync("inbox_results.csv", rows.join("\n"));
console.log(`n=${n} classification=${((correct / n) * 100).toFixed(1)}% unsafe_drafts=${unsafe} errors=${errors} -> inbox_results.csv`);
