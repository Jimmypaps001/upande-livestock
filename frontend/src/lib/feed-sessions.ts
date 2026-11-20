/* ── Feeding a herd's day in one session or two ──
   Wire shapes of serverscripts/feeding/_sessions.py. A day is Full, or Half-1
   then Half-2; the sessions that stand add up to how much has been fed. */

export type SessionKey = "Full" | "Half-1" | "Half-2";
/** What the desk asks for; "Half" is the next half, the server numbers it. */
export type SessionChoice = "Full" | "Half";
export type DayState = "not_fed" | "half_fed" | "fully_fed";

export type SessionComponent = {
  item_code: string;
  item_name: string;
  uom: string;
  planned_kg: number;
  fed_kg: number;
};

export type FeedSession = {
  name?: string;
  feed_session: SessionKey;
  label: string;
  session_fraction: number;
  source: "System" | "Day sheet";
  status: "Fed" | "Waiting for stock" | "Cancelled";
  planned_kg: number;
  fed_kg: number;
  amended: boolean | 0 | 1;
  components: SessionComponent[];
  fed_on?: string | null;
  overridden?: boolean | 0 | 1;
};

export type SessionState = {
  state: DayState;
  label: string;
  fed_fraction: number;
  remaining_fraction: number;
  choices: SessionKey[];
  next_session: SessionKey | null;
  second_due: boolean;
  can_override: boolean;
  sessions: FeedSession[];
};

export const SESSION_LABEL: Record<SessionKey, string> = {
  Full: "Full day",
  "Half-1": "Half day, session 1 of 2",
  "Half-2": "Half day, session 2 of 2",
};

export const STATE_LABEL: Record<DayState, string> = {
  not_fed: "Not fed",
  half_fed: "Half fed (1 of 2)",
  fully_fed: "Fully fed",
};

export function stateLabel(s?: Pick<SessionState, "state" | "label"> | null): string {
  return s ? s.label || STATE_LABEL[s.state] : STATE_LABEL.not_fed;
}

/** The choice to preselect: the second half once a half is fed, else a full day. */
export function defaultChoice(s?: SessionState | null): SessionChoice {
  return s?.state === "half_fed" ? "Half" : "Full";
}

/** Wording of the choice for this day, e.g. "Half day, session 2 of 2". */
export function choiceLabel(choice: SessionChoice, s?: SessionState | null): string {
  if (choice === "Full") return SESSION_LABEL.Full;
  return SESSION_LABEL[s?.state === "half_fed" ? "Half-2" : "Half-1"];
}

/** Would this choice feed more than a day (or repeat a session)? Needs a manager's confirm. */
export function needsOverride(choice: SessionChoice, s?: SessionState | null): boolean {
  if (!s) return false;
  if (s.state === "fully_fed") return true;
  if (s.state === "half_fed") return choice === "Full" || s.next_session === null;
  return false;
}

/** The choices this user may make: past a full day is a manager's override, so
 *  anyone else is not offered it (a fully fed herd offers them nothing). */
export function allowedChoices(s: SessionState | null | undefined, mayOverride: boolean): SessionChoice[] {
  return (["Full", "Half"] as SessionChoice[]).filter((c) => mayOverride || !needsOverride(c, s));
}

/** The sentence the confirm dialog shows. */
export function overrideSentence(choice: SessionChoice, s: SessionState): string {
  return `${s.label}. Feeding ${choiceLabel(choice, s).toLowerCase()} now is more than a full day.`;
}

/** One chip line: "Half day, session 1 of 2: 20 kg Calves Meal (amended)". */
export function sessionChipText(s: FeedSession): string {
  const amended = !!s.amended;
  const parts = s.components
    .filter((c) => c.fed_kg > 0)
    .map((c) => `${round(c.fed_kg)} ${c.uom === "Kilogram" || !c.uom ? "kg" : c.uom} ${c.item_name}`);
  const what = parts.length ? parts.join(", ") : `${round(s.fed_kg)} kg`;
  return `${s.label}: ${what}${amended ? " (amended)" : ""}${s.status === "Waiting for stock" ? ", waiting for stock" : ""}`;
}

/** Planned vs fed for one session, e.g. "planned 45 kg, fed 50 kg". */
export function sessionFigures(s: FeedSession): string {
  return `planned ${round(s.planned_kg)} kg, fed ${round(s.fed_kg)} kg`;
}

export function secondSessionDue(s?: Pick<SessionState, "second_due" | "state"> | null): boolean {
  return !!s && (s.second_due || s.state === "half_fed");
}

/** The herds that owe a second session, for the banner. */
export function dueHerds<T extends { herd: string; herd_name?: string; session?: SessionState | null }>(
  days: T[] | null | undefined,
): T[] {
  return (days ?? []).filter((d) => secondSessionDue(d.session));
}

function round(n: number): number {
  return Math.round(n * 1000) / 1000;
}
