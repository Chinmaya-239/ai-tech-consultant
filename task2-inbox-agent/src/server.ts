import express from "express";
import { processEmail } from "./agent.js";
import { load, save, sendOnce } from "./store.js";
import { recordOutcome, unchanged, canAutoSend, enableCategory, disableCategory, THRESHOLD } from "./autonomy.js";
import { CATEGORIES, type Category } from "./types.js";

const app = express(); app.use(express.json({ limit: "200kb" })); app.use(express.static("public"));
const wrap = (f: express.RequestHandler): express.RequestHandler => (q, s, n) => Promise.resolve(f(q, s, n)).catch((e) => s.status(500).json({ error: String(e) }));

app.post("/emails", wrap(async (req, res) => {
  const { from, subject, body } = req.body ?? {};
  if (typeof body !== "string" || body.length < 3 || body.length > 20000) return res.status(400).json({ error: "body (3-20000 chars) required" });
  const i = await processEmail({ from: String(from ?? "customer@example.com"), subject: String(subject ?? "(no subject)"), body });
  const db = load();
  if (canAutoSend(db.autonomy, i) && i.draft) {              // controlled autonomy: every gate re-checked per email
    sendOnce(db, i, i.draft.reply, true); i.state = "sent"; i.final = i.draft.reply; i.decision = "auto_sent";
  }
  db.interactions.push(i); save(db); res.json(i);
}));
app.get("/inbox", (_q, res) => res.json(load().interactions.slice().reverse()));
app.get("/autonomy", (_q, res) => { const a = load().autonomy; res.json({ threshold: THRESHOLD, categories: Object.fromEntries(CATEGORIES.map((c) => [c, a[c] ?? { streak: 0, eligible: false, enabled: false }])) }); });

// action: approve (sends draft as-is or with finalText) | reject (finalText = human's own reply) | expert
app.post("/review/:id", wrap((req, res) => {
  const db = load(); const i = db.interactions.find((x) => x.id === req.params.id);
  if (!i) return res.status(404).json({ error: "not found" });
  if (i.state === "sent" || i.state === "rejected") return res.status(409).json({ error: "already decided" });
  const { action, finalText, reason } = req.body ?? {};
  if (action === "expert") { i.state = "needs_expert"; save(db); return res.json(i); }
  if (!i.draft && action === "approve") return res.status(400).json({ error: "no draft (knowledge service was unavailable) - write a reply and use reject" });
  const final = String(finalText ?? i.draft?.reply ?? "");
  if (final.length < 3) return res.status(400).json({ error: "reply text required" });
  const same = action === "approve" && !!i.draft && unchanged(i.draft.reply, final);   // compares text, not the button click
  i.final = final; i.editReason = reason; i.state = action === "reject" ? "rejected" : "sent";
  i.decision = action === "reject" ? "rejected" : same ? "approved_unchanged" : "approved_edited";
  sendOnce(db, i, final, false);
  db.autonomy = recordOutcome(db.autonomy, i, same); save(db); res.json({ interaction: i, autonomy: db.autonomy[i.classification.category] });
}));
app.post("/autonomy/:cat/:op", wrap((req, res) => {
  const db = load(); const cat = req.params.cat as Category;
  if (!CATEGORIES.includes(cat)) return res.status(400).json({ error: "bad category" });
  try { db.autonomy = req.params.op === "enable" ? enableCategory(db.autonomy, cat) : disableCategory(db.autonomy, cat, "manual kill switch"); }
  catch (e) { return res.status(409).json({ error: String(e) }); }
  save(db); res.json(db.autonomy[cat]);
}));
app.get("/health", (_q, res) => res.json({ ok: true }));
const port = Number(process.env.INBOX_PORT ?? 8002); app.listen(port, () => console.log(`Inbox agent on :${port}`));
