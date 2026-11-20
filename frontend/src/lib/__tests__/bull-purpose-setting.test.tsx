import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SettingField } from "@/components/settings/SettingField";
import type { SettingsField } from "@/lib/settings";

const field: SettingsField = {
  fieldname: "bull_purpose", label: "Bull Purpose", fieldtype: "Select",
  options: "Cull for sale at birth\nFattening\nBreeding", description: null,
  default: "Cull for sale at birth", depends_on: null, reqd: false, zero: null, posts: false,
};

describe("the Bull purpose setting", () => {
  it("shows the Kaitet default while nothing is stored", () => {
    render(<SettingField field={field} stored={null} value={null} onChange={() => {}} />);
    expect(screen.getByRole("combobox").textContent).toContain("Cull for sale at birth");
  });

  it("offers the three purposes and reports the choice", () => {
    const onChange = vi.fn();
    render(<SettingField field={field} stored="Fattening" value="Fattening" onChange={onChange} />);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Cull for sale at birth", "Fattening", "Breeding"]);
    fireEvent.click(screen.getByRole("option", { name: "Breeding" }));
    expect(onChange).toHaveBeenCalledWith("Breeding");
  });
});
