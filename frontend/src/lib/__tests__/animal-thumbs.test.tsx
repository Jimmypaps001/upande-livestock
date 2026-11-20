import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import type { AnimalSummary } from "@/lib/animals";

const base: AnimalSummary = {
  id: "B001/19", name: "BRUNO", sex: "Male", herd: "Finishing 1", breed: "Boran",
  bornOn: "2023-01-01", status: "Active", stage: "open", photo: "/files/bull.jpg",
};

function imgs(animals: AnimalSummary[]) {
  const { container } = render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
  return Array.from(container.querySelectorAll("img"));
}

describe("list thumbnails", () => {
  it("a row loads the thumbnail, lazily, never the full image", () => {
    const [img] = imgs([{ ...base, thumb: "/files/bull_thumb.jpg" }]);
    expect(img.getAttribute("src")).toBe("/files/bull_thumb.jpg");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.getAttribute("decoding")).toBe("async");
  });

  it("falls back to the full image when there is no thumbnail", () => {
    const [img] = imgs([base]);
    expect(img.getAttribute("src")).toBe("/files/bull.jpg");
  });

  it("draws no image when there is no photo", () => {
    expect(imgs([{ ...base, photo: null, thumb: null }])).toHaveLength(0);
  });
});
