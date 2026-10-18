import fs from "node:fs";
import type { Interaction } from "./types.js";
import type { AutonomyState } from "./autonomy.js";
const FILE = process.env.INBOX_STORE ?? "data/store.json";
interface Db { interactions: Interaction[]; autonomy: AutonomyState; outbox: { id: string; to: string; body: string; at: string; auto: boolean }[] }
export function load(): Db {
  try { return JSON.parse(fs.readFileSync(FILE, "utf8")) as Db; } catch { return { interactions: [], autonomy: {}, outbox: [] }; }
}
export function save(db: Db): void { fs.mkdirSync("data", { recursive: true }); fs.writeFileSync(FILE, JSON.stringify(db, null, 1)); }
/** Idempotent simulated send: the same interaction id can never be sent twice (prevents duplicates after retries). */
export function sendOnce(db: Db, i: Interaction, body: string, auto: boolean): boolean {
  if (db.outbox.some((o) => o.id === i.id)) return false;
  db.outbox.push({ id: i.id, to: i.email.from, body, at: new Date().toISOString(), auto }); return true;
}
