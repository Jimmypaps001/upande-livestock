import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Capabilities } from "@/lib/frappe";
import { allowedChoices } from "@/lib/feed-sessions";
import { landingView, viewOpen, VIEW_NEEDS } from "@/lib/roles";
import { visibleTabs, type LivestockSettingsDoc } from "@/lib/settings";

vi.mock("@/hooks/use-notifications", () => ({
  useUnreadNotifications: () => ({ unread: 0, refresh: async () => {}, setUnread: () => {} }),
}));

import { AppSidebar } from "@/components/AppSidebar";
import { SidebarProvider } from "@/components/ui/sidebar";

/**
 * "If someone should not access something, remove it from their view."
 *
 * Each role below carries the `can` map the server builds for it
 * (serverscripts/common/capabilities.py), taken from the shipped DocPerms.
 * Everything a role cannot use must be ABSENT — not greyed, not refused.
 */
function caps(o: {
  read?: string[]; create?: string[]; write?: string[]; flags?: Partial<Record<string, boolean>>;
}): Capabilities {
  const m = (names: string[] = []) => Object.fromEntries(names.map((n) => [n, true]));
  return {
    read: m([...(o.read ?? []), "Notification Log"]), create: m(o.create), write: m(o.write),
    stock: false, post_draft: false, override_feed: false, insure: false, accounts: false,
    appreciate: false, cull_vet: false, cull_manager: false, quality: false, manage_sires: false, operator: false,
    ...o.flags,
  } as Capabilities;
}

const ALL_READ = ["Animal", "Herds", "Livestock Event", "Livestock Health Case", "Livestock Weight Record",
  "Milk Recording", "Milk Quality Test", "Livestock Disposal", "Livestock Vet", "Livestock Loss",
  "Livestock Loss Scenario", "Livestock Insurance Claim", "Livestock Settings", "BOM", "Item", "Notification Log", "Livestock Sire"];

const ROLES: Record<string, { roles: string[]; can: Capabilities }> = {
  manager: {
    roles: ["Livestock Manager"],
    can: caps({
      read: ALL_READ,
      create: ["Livestock Event", "Livestock Health Case", "Livestock Diagnosis", "Livestock Weight Record", "Milk Recording",
        "Milk Quality Test", "Livestock Disposal", "Livestock Vet", "Livestock Loss", "Livestock Loss Scenario",
        "Herds", "Animal", "BOM", "Livestock Feed Actual"],
      write: ["Livestock Disposal", "Livestock Insurance Claim", "Livestock Settings", "BOM", "Animal"],
      flags: { stock: true, post_draft: true, override_feed: true, appreciate: true, cull_manager: true, quality: true, manage_sires: true },
    }),
  },
  milker: {
    roles: ["Livestock Milker"],
    can: caps({
      read: ["Animal", "Herds", "Livestock Event", "Livestock Health Case", "Milk Recording", "Milk Quality Test",
        "Livestock Loss Scenario", "Livestock Settings", "Item"],
      create: ["Milk Recording"],
    }),
  },
  attendant: {
    roles: ["Livestock Attendant"],
    can: caps({
      read: ["Animal", "Herds", "Livestock Event", "Livestock Health Case", "Livestock Weight Record", "Milk Recording",
        "Milk Quality Test", "Livestock Vet", "Livestock Loss Scenario", "Livestock Settings", "BOM", "Item"],
      create: ["Livestock Event", "Livestock Weight Record", "Livestock Loss"],
    }),
  },
  quality: {
    roles: ["Livestock Quality"],
    can: caps({ read: ["Milk Recording", "Milk Quality Test"], create: ["Milk Quality Test"], flags: { quality: true } }),
  },
  accounts: {
    roles: ["Accounts Manager"],
    can: caps({
      read: ["Livestock Loss", "Livestock Loss Scenario", "Livestock Settings", "Item"],
      flags: { insure: true, accounts: true, appreciate: true },
    }),
  },
  vet: {
    roles: ["Livestock Vet"],
    can: caps({
      read: ["Animal", "Herds", "Livestock Event", "Livestock Health Case", "Livestock Weight Record", "Livestock Disposal",
        "Livestock Vet", "Livestock Loss", "Livestock Loss Scenario", "Livestock Insurance Claim", "Livestock Settings", "Item"],
      create: ["Livestock Event", "Livestock Health Case", "Livestock Diagnosis", "Livestock Loss"],
      write: ["Livestock Disposal"],
      flags: { cull_vet: true },
    }),
  },
};

const open = (who: keyof typeof ROLES, view: string) =>
  viewOpen(view as never, ROLES[who].roles, [], ROLES[who].can);

describe("which screens each role is shown", () => {
  it("a Livestock Manager is shown every screen", () => {
    for (const v of Object.keys(VIEW_NEEDS)) expect(open("manager", v), v).toBe(true);
  });

  it("a milker records milk and reads the herd: no stock, quality filing, culling, claims or vets", () => {
    for (const v of ["milking", "animals", "dashboard"]) expect(open("milker", v), v).toBe(true);
    for (const v of ["feed-quality", "quality"]) expect(open("milker", v), v).toBe(false);
    for (const v of ["transactions", "feeding", "procurement", "ration-editor", "culling", "claims", "vets", "herds", "movement", "weight", "treatment"])
      expect(open("milker", v), v).toBe(false);
  });

  it("an attendant records events and weights but not milk, stock, culling or claims", () => {
    for (const v of ["movement", "calving", "weight", "animals"]) expect(open("attendant", v), v).toBe(true);
    for (const v of ["milking", "transactions", "feeding", "culling", "claims", "ration-editor", "treatment", "check-up"])
      expect(open("attendant", v), v).toBe(false);
  });

  it("the lab is shown Quality and Quality & Feed and nothing else", () => {
    const shown = Object.keys(VIEW_NEEDS).filter((v) => open("quality", v));
    expect(shown.sort()).toEqual(["feed-quality", "quality"]);
    expect(landingView(ROLES.quality.roles, [], ROLES.quality.can)).toBe("quality");
  });

  it("an Accounts Manager is shown Settings, Claims and Loss scenarios, not the herd or the stores", () => {
    for (const v of ["settings", "claims", "loss-scenarios"]) expect(open("accounts", v), v).toBe(true);
    for (const v of ["animals", "feeding", "milking", "quality", "culling", "vets", "dashboard", "transactions", "herds"])
      expect(open("accounts", v), v).toBe(false);
    expect(landingView(ROLES.accounts.roles, [], ROLES.accounts.can)).toBe("settings");
  });

  it("a vet is shown the clinical screens and culling, not feeding, milking or quality", () => {
    for (const v of ["check-up", "treatment", "health-case", "culling", "animals", "vets"]) expect(open("vet", v), v).toBe(true);
    for (const v of ["feeding", "milking", "quality", "transactions", "procurement", "ration-editor", "herds"]) expect(open("vet", v), v).toBe(false);
  });
});

describe("the sidebar leaves out what a role cannot open", () => {
  beforeAll(() => {
    window.matchMedia = ((q: string) => ({
      matches: false, media: q, onchange: null, addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
  });
  afterEach(() => {
    cleanup();
    delete window.LIVESTOCK;
  });

  function sidebar(who: keyof typeof ROLES) {
    window.LIVESTOCK = { bootstrap: { user: "u@x.com", full_name: "U", roles: ROLES[who].roles, can: ROLES[who].can } };
    render(
      <SidebarProvider>
        <AppSidebar view="dashboard" onNavigate={() => {}} />
      </SidebarProvider>,
    );
  }
  // By route, not by label: the menu's wording comes from the event catalog.
  const routes = () => screen.queryAllByRole("link").map((a) => a.getAttribute("href") ?? "");
  const absent = (...views: string[]) => views.forEach((v) => expect(routes(), v).not.toContain(`#/${v}`));
  const present = (...views: string[]) => views.forEach((v) => expect(routes(), v).toContain(`#/${v}`));
  const groups = (...names: string[]) => names.forEach((n) => expect(screen.queryAllByText(n).length, n).toBeGreaterThan(0));
  const noGroups = (...names: string[]) => names.forEach((n) => expect(screen.queryAllByText(n).length, n).toBe(0));

  it("Livestock Manager sees every group", () => {
    sidebar("manager");
    groups("Herd", "Operations", "People", "Configuration");
    present("transactions", "culling", "settings", "vets", "claims", "sires");
  });

  it("Milker: no People or Configuration group, no Transactions, Culling, Feeding items", () => {
    sidebar("milker");
    noGroups("People", "Servicing");
    absent("vets", "claims", "transactions", "culling", "procurement", "ration-editor", "herds", "movement", "feeding", "sires");
    present("milking");
    absent("quality", "feed-quality");
  });

  it("Attendant: no Milking, Culling, Claims", () => {
    sidebar("attendant");
    absent("milking", "culling", "claims", "transactions", "ration-editor", "treatment", "sires");
    present("movement", "weight");
  });

  it("Livestock Quality only: just the two quality items", () => {
    sidebar("quality");
    present("quality", "feed-quality");
    absent("animals", "feeding", "vets", "milking", "settings", "notifications", "culling");
    noGroups("Herd", "People", "Configuration", "Servicing");
  });

  it("Accounts Manager only: Configuration alone", () => {
    sidebar("accounts");
    present("settings", "claims", "loss-scenarios");
    groups("Configuration");
    noGroups("Herd", "Operations", "People", "Servicing");
    absent("animals", "milking", "transactions", "feeding");
  });

  it("Vet: no Feeding group, no Milking or Quality", () => {
    sidebar("vet");
    absent("feeding", "milking", "quality", "transactions", "procurement", "herds");
    present("check-up", "treatment", "culling", "vets");
    absent("sires");
  });
});

describe("settings tabs", () => {
  const tab = (fieldname: string, field: string) => ({
    fieldname, label: fieldname,
    sections: [{ fieldname: `${fieldname}_s`, label: null, description: null, tables: [], fields: [{ fieldname: field }] }],
  });
  const doc = (can_write: boolean, writable?: string[]) =>
    ({ tabs: [tab("tab_general", "a"), tab("tab_accounts", "b")], can_write, writable }) as unknown as LivestockSettingsDoc;

  it("an Accounts Manager is shown only the Accounts tab", () => {
    expect(visibleTabs(doc(false, ["b"])).map((t) => t.fieldname)).toEqual(["tab_accounts"]);
  });
  it("a manager and a read-only user are shown every tab", () => {
    expect(visibleTabs(doc(true, ["a", "b"]))).toHaveLength(2);
    expect(visibleTabs(doc(false, []))).toHaveLength(2);
  });
});

describe("feeding choices", () => {
  const fed = { state: "fully_fed", next_session: null } as never;
  const half = { state: "half_fed", next_session: 2 } as never;
  it("a non-manager is not offered more than a day", () => {
    expect(allowedChoices(fed, false)).toEqual([]);
    expect(allowedChoices(half, false)).toEqual(["Half"]);
    expect(allowedChoices(fed, true)).toEqual(["Full", "Half"]);
  });
});
