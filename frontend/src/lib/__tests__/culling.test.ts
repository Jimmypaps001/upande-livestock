import { describe, expect, it } from "vitest";
import { asSummaries, DEATH_CAUSES, FLOWS, toneFor, type FarmAnimal } from "@/lib/culling";

const animal: FarmAnimal = {
  name: "A039/26",
  burn_name: "APIJA",
  sex: "Female",
  current_herd: "Lactating group 1",
  breed: "Ayrshire",
  date_of_birth: "2022-04-11",
  image: null,
};

describe("the roster the search reads", () => {
  it("shows the farm's name for her and keeps the register number as the id", () => {
    // The register number is the record — it is what every other screen, and
    // the register book on the wall, calls her. The name is what the herdsman
    // shouts at her, so it leads and the number follows.
    const [got] = asSummaries([animal]);
    expect(got.id).toBe("A039/26");
    expect(got.name).toBe("APIJA");
  });

  it("falls back to the number when nobody has named her", () => {
    const [got] = asSummaries([{ ...animal, burn_name: null }]);
    expect(got.name).toBe("A039/26");
  });

  it("says 'no herd' rather than leaving a blank where a herd should be", () => {
    const [got] = asSummaries([{ ...animal, current_herd: null }]);
    expect(got.herd).toBe("no herd");
  });

  it("marks everyone active, because the board only serves animals still here", () => {
    const [got] = asSummaries([animal]);
    expect(got.status).toBe("Active");
  });
});

describe("what a case is waiting on", () => {
  it("distinguishes the two gates from the two endings", () => {
    // A queue that colours "with the vet" the same as "with the manager" is a
    // queue neither of them checks; one that colours "refused" like "posted"
    // is one where a case nobody agreed to looks like a cow that has gone.
    expect(toneFor("Awaiting Vet")).toBe("wait");
    expect(toneFor("Awaiting Approval")).toBe("wait");
    expect(toneFor("Approved")).toBe("ready");
    expect(toneFor("Posted")).toBe("done");
    expect(toneFor("Rejected")).toBe("stopped");
  });
});

describe("the vocabulary the page offers", () => {
  it("offers exactly the four ways an animal leaves", () => {
    expect(FLOWS.map((f) => f.flow)).toEqual(["Sale", "Disposal", "Mortality", "Gift"]);
  });

  it("has no free-text escape in the causes of death", () => {
    // "Sick" typed forty ways is why no farm can say what it loses cows to.
    expect(DEATH_CAUSES).toContain("Unknown");
    expect(DEATH_CAUSES.some((c) => /other/i.test(c))).toBe(true);
    expect(DEATH_CAUSES).not.toContain("");
  });
});
