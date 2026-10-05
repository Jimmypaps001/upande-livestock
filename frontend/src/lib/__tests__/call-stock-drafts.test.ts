import { afterEach, describe, expect, it, vi } from "vitest";
import { call } from "@/lib/frappe";

/** Any endpoint whose record stood while its stock issue was saved as a draft
 *  says so in `stock_drafts`; `call` passes that on to the page as an event. */

afterEach(() => vi.unstubAllGlobals());

const answer = (message: unknown) =>
  vi.fn(async () => new Response(JSON.stringify({ message }), { status: 200 }));

describe("call hears of stock drafts", () => {
  it("announces the drafts an answer carries", async () => {
    vi.stubGlobal("fetch", answer({ ok: true, stock_drafts: [{ name: "STE-1", stock_entry_type: "Livestock Vaccination", short: "x" }] }));
    const heard = vi.fn();
    window.addEventListener("livestock:stock-drafts", heard);
    const r = await call("any.method");
    window.removeEventListener("livestock:stock-drafts", heard);
    expect((r as { ok: boolean }).ok).toBe(true);
    expect(heard).toHaveBeenCalledTimes(1);
    expect((heard.mock.calls[0][0] as CustomEvent).detail[0].name).toBe("STE-1");
  });

  it("says nothing when there are none", async () => {
    vi.stubGlobal("fetch", answer({ ok: true }));
    const heard = vi.fn();
    window.addEventListener("livestock:stock-drafts", heard);
    await call("any.method");
    window.removeEventListener("livestock:stock-drafts", heard);
    expect(heard).not.toHaveBeenCalled();
  });
});
