import { ALWAYS_HUMAN, type Category, type Interaction } from "./types.js";

export const THRESHOLD = 20;
/** "Same kind" = same classifier category AND low risk AND knowledge-backed (sources present).
 *  "Without changing" = final text equals the generated draft after trimming + whitespace collapse (case preserved). */
export const norm = (s: string) => s.replace(/\s+/g, " ").trim();
export const unchanged = (draft: string, final: string) => norm(draft) === norm(final);

export interface CatState { streak: number; eligible: boolean; enabled: boolean; disabledReason?: string; history: boolean[] }
export type AutonomyState = Partial<Record<Category, CatState>>;
const fresh = (): CatState => ({ streak: 0, eligible: false, enabled: false, history: [] });

/** Called for every human decision (and post-hoc audit of auto-sent mails). Returns updated state. */
export function recordOutcome(state: AutonomyState, i: Interaction, wasUnchanged: boolean): AutonomyState {
  const cat = i.classification.category;
  const s = state[cat] ?? fresh();
  const qualifies = !ALWAYS_HUMAN.has(cat) && i.classification.risk === "low" && !!i.draft && i.draft.sources.length > 0 && i.policyFlags.length === 0;
  s.history = [...s.history, wasUnchanged && qualifies].slice(-20);
  if (wasUnchanged && qualifies) s.streak += 1; else s.streak = 0;                  // any edit/reject/failed check resets
  s.eligible = s.streak >= THRESHOLD;
  if (s.enabled && !(wasUnchanged && qualifies)) { s.enabled = false; s.disabledReason = `quality drop on ${i.id}`; }   // automatic demotion
  return { ...state, [cat]: s };
}

/** Eligibility is NOT permission: a human must switch the category on (enableCategory). Auto-send also re-checks every safety condition per email. */
export function enableCategory(state: AutonomyState, cat: Category): AutonomyState {
  if (ALWAYS_HUMAN.has(cat)) throw new Error(`${cat} can never be autonomous`);
  const s = state[cat]; if (!s?.eligible) throw new Error(`${cat} not eligible (${s?.streak ?? 0}/${THRESHOLD})`);
  return { ...state, [cat]: { ...s, enabled: true, disabledReason: undefined } };
}
export function disableCategory(state: AutonomyState, cat: Category, reason: string): AutonomyState {
  const s = state[cat] ?? fresh(); return { ...state, [cat]: { ...s, enabled: false, eligible: false, streak: 0, disabledReason: reason } };
}
export function canAutoSend(state: AutonomyState, i: Interaction): boolean {
  const s = state[i.classification.category];
  return !!s?.enabled && !ALWAYS_HUMAN.has(i.classification.category) && i.classification.risk === "low" && !!i.draft &&
    !i.draft.needs_human && i.draft.sources.length > 0 && i.policyFlags.length === 0 && i.state === "pending_review";
}
