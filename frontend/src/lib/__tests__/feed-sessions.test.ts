import { describe, expect, it } from "vitest";
import {
  choiceLabel,
  defaultChoice,
  dueHerds,
  needsOverride,
  sessionChipText,
  stateLabel,
  type FeedSession,
  type SessionState,
} from "@/lib/feed-sessions";

const st = (state: SessionState["state"], extra: Partial<SessionState> = {}): SessionState => ({
  state,
  label: { not_fed: "Not fed", half_fed: "Half fed (1 of 2)", fully_fed: "Fully fed" }[state],
  fed_fraction: state === "not_fed" ? 0 : state === "half_fed" ? 0.5 : 1,
  remaining_fraction: 0,
  choices: [],
  next_session: state === "half_fed" ? "Half-2" : null,
  second_due: state === "half_fed",
  can_override: true,
  sessions: [],
  ...extra,
});

describe("feed sessions", () => {
  it("preselects the second half once a half is fed, else a full day", () => {
    expect(defaultChoice(st("not_fed"))).toBe("Full");
    expect(defaultChoice(st("half_fed"))).toBe("Half");
    expect(defaultChoice(undefined)).toBe("Full");
  });

  it("words the half as session 1 or 2 of 2", () => {
    expect(choiceLabel("Half", st("not_fed"))).toBe("Half day, session 1 of 2");
    expect(choiceLabel("Half", st("half_fed"))).toBe("Half day, session 2 of 2");
    expect(choiceLabel("Full", st("not_fed"))).toBe("Full day");
  });

  it("asks for an override only when more than a day would be fed", () => {
    expect(needsOverride("Full", st("not_fed"))).toBe(false);
    expect(needsOverride("Half", st("not_fed"))).toBe(false);
    expect(needsOverride("Half", st("half_fed"))).toBe(false);
    expect(needsOverride("Full", st("half_fed"))).toBe(true);
    expect(needsOverride("Half", st("fully_fed"))).toBe(true);
    expect(needsOverride("Full", undefined)).toBe(false);
  });

  it("labels the day's state", () => {
    expect(stateLabel(st("half_fed"))).toBe("Half fed (1 of 2)");
    expect(stateLabel(null)).toBe("Not fed");
  });

  it("writes a session chip with the amendment", () => {
    const s: FeedSession = {
      feed_session: "Half-1", label: "Half day, session 1 of 2", session_fraction: 0.5, source: "Day sheet",
      status: "Fed", planned_kg: 45, fed_kg: 20, amended: true,
      components: [{ item_code: "CM", item_name: "Calves Meal", uom: "Kilogram", planned_kg: 45, fed_kg: 20 }],
    };
    expect(sessionChipText(s)).toBe("Half day, session 1 of 2: 20 kg Calves Meal (amended)");
  });

  it("lists the herds that owe a second session", () => {
    const days = [
      { herd: "A", session: st("half_fed") },
      { herd: "B", session: st("fully_fed") },
      { herd: "C" },
    ];
    expect(dueHerds(days).map((d) => d.herd)).toEqual(["A"]);
  });
});
