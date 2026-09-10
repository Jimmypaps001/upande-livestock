import type { RecipeLine } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

/**
 * What is in one row's mix — item, quantity, unit — for a Rations or
 * Concentrate row expanded open.
 *
 * `qty` is shown exactly as the server sent it, in RECIPE unit of measure —
 * hay reads "2.0 Kilogram" here, never "0.14 BALE". Nothing in this
 * component converts a unit; see ManualConfig's and RecipePicker's module
 * docs for why that conversion never happens on the client.
 *
 * `lines` being `undefined` and `lines` being `[]` are different messages
 * and are shown as such: `undefined` means the endpoint behind this row does
 * not carry ingredient detail yet, `[]` means it does and this particular
 * run recorded none.
 */
export function IngredientLines({ lines }: { lines: RecipeLine[] | undefined }) {
  if (lines === undefined) {
    return (
      <p className="px-3 py-2.5 text-[12px] text-[var(--sd-quiet)]">
        Ingredient detail is not available for this row yet.
      </p>
    );
  }
  if (!lines.length) {
    return (
      <p className="px-3 py-2.5 text-[12px] text-[var(--sd-quiet)]">
        No ingredient lines recorded for this row.
      </p>
    );
  }
  return (
    <table className="w-full text-[12px]">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
          <th className="px-3 py-1.5 font-medium">Ingredient</th>
          <th className="px-3 py-1.5 text-right font-medium">Quantity</th>
        </tr>
      </thead>
      <tbody>
        {lines.map((ln) => (
          <tr key={ln.item_code} className="border-t border-[var(--sd-line-soft)]">
            <td className="px-3 py-1.5 text-[var(--sd-ink)]">{ln.item_name || ln.item_code}</td>
            <td className="px-3 py-1.5 text-right tabular-nums text-[var(--sd-muted)]">
              {fmt(ln.qty)} <span className="text-[11px] text-[var(--sd-quiet)]">{ln.uom}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
