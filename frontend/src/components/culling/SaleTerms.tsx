import { useEffect, useRef, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { BuyerPicker } from "@/components/culling/BuyerPicker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSalePreview, type SaleDraft, type SalePreview } from "@/lib/culling";
import { isError } from "@/lib/frappe";
import { fmt } from "@/lib/utils";

const SELECT = "h-9 rounded-md border border-input bg-background px-3 text-sm";

/**
 * The terms of a sale and the invoice they make.
 *
 * Pick the buyer and everything the Sales Invoice needs is fetched: the buyer's
 * PIN, contact, payment terms and receivable account, the cost centre of her herd,
 * the farm and business unit, the taxes. What the server cannot find is listed in
 * plain words and keeps the sale from being approved, so Accounts is never handed
 * a draft it has to finish.
 */
export function SaleTerms({
  animal,
  postingDate,
  draft,
  onDraft,
  onReady,
}: {
  animal: string;
  postingDate?: string;
  draft: SaleDraft;
  onDraft: (next: SaleDraft) => void;
  onReady: (ready: boolean) => void;
}) {
  const [preview, setPreview] = useState<SalePreview | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const set = (patch: Partial<SaleDraft>) => onDraft({ ...draft, ...patch });
  const ready = useRef(onReady);
  ready.current = onReady;

  const key = JSON.stringify([animal, postingDate, draft]);
  useEffect(() => {
    if (!draft.customer) {
      setPreview(null);
      setFailure(null);
      ready.current(false);
      return;
    }
    let live = true;
    setLoading(true);
    const t = setTimeout(async () => {
      const r = await getSalePreview(animal, draft, postingDate);
      if (!live) return;
      setLoading(false);
      if (isError(r)) {
        setFailure(r.error);
        setPreview(null);
        ready.current(false);
        return;
      }
      setFailure(null);
      setPreview(r);
      ready.current(!r.missing.length && !!r.lines.length);
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const buyer = preview?.customer ?? null;
  const t = preview?.terms;
  const kg = draft.price_basis === "Per kg";

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="sale-buyer">Buyer</Label>
          <BuyerPicker label="Buyer" value={draft.customer} onChange={(customer) => set({ customer })} />
        </div>

        {buyer && (
          <dl className="grid gap-x-6 gap-y-1 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3 text-[12.5px] sm:col-span-2 sm:grid-cols-2">
            <Detail label="Customer" value={buyer.customer_name || buyer.name} />
            <Detail label="Phone" value={buyer.mobile_no} />
            <Detail label="KRA PIN" value={buyer.tax_id} />
            <Detail label="Email" value={buyer.email_id} />
            <Detail label="Address" value={buyer.address} />
            <Detail label="Group / territory" value={[buyer.customer_group, buyer.territory].filter(Boolean).join(" · ")} />
            <Detail label="Billing" value={[buyer.default_currency, buyer.default_price_list].filter(Boolean).join(" · ")} />
            <Detail label="Receivable" value={buyer.receivable} />
          </dl>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sale-basis">Priced</Label>
          <select
            id="sale-basis"
            className={SELECT}
            value={draft.price_basis}
            onChange={(e) => set({ price_basis: e.target.value as SaleDraft["price_basis"] })}
          >
            <option value="Per head">Per head</option>
            <option value="Per kg">Per kg x weight</option>
          </select>
        </div>
        {kg ? (
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sale-rate">Rate per kg</Label>
              <Input id="sale-rate" type="number" min={0} value={draft.rate} onChange={(e) => set({ rate: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sale-weight">Weight (kg)</Label>
              <Input
                id="sale-weight"
                type="number"
                min={0}
                value={draft.weight_kg}
                placeholder={preview?.weight_kg ? `Last ${preview.weight_kg}` : ""}
                onChange={(e) => set({ weight_kg: e.target.value })}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ap-price">Price</Label>
            <Input
              id="ap-price"
              type="number"
              min={0}
              value={draft.sale_price}
              onChange={(e) => set({ sale_price: e.target.value })}
            />
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sale-terms">Payment terms</Label>
          <select
            id="sale-terms"
            className={SELECT}
            value={draft.payment_terms}
            onChange={(e) => set({ payment_terms: e.target.value })}
          >
            <option value="">{t?.payment_terms ? `Buyer's: ${t.payment_terms}` : "Due on the day"}</option>
            {preview?.options.payment_terms.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sale-mode">Mode of payment (optional)</Label>
          <select
            id="sale-mode"
            className={SELECT}
            value={draft.mode_of_payment}
            onChange={(e) => set({ mode_of_payment: e.target.value })}
          >
            <option value="">Not stated (M-Pesa buyers)</option>
            {preview?.options.modes_of_payment.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>

      {failure && <Notice tone="error">{failure}</Notice>}
      {preview && !!preview.missing.length && (
        <Notice tone="error">{preview.missing.join("\n")}</Notice>
      )}
      {preview?.notes.map((n) => (
        <Notice key={n} tone="info">
          {n}
        </Notice>
      ))}

      {preview && !!preview.lines.length && t && (
        <div className="flex flex-col gap-2" aria-label="Invoice preview">
          <p className="text-[12px] font-medium uppercase tracking-wide text-[var(--sd-muted)]">
            Draft Sales Invoice for Accounts {loading ? "(updating)" : ""}
          </p>
          <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] shadow-[var(--sd-shadow-inset)]">
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-[var(--sd-muted)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Item</th>
                  <th className="px-3 py-2 text-right font-medium">Qty</th>
                  <th className="px-3 py-2 text-right font-medium">Rate</th>
                  <th className="px-3 py-2 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {preview.lines.map((l) => (
                  <tr key={l.item_code + (l.asset ?? "")}>
                    <td className="px-3 py-2">
                      {l.item_name}
                      {l.asset && <span className="block text-[11px] text-[var(--sd-muted)]">{l.asset}</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {l.qty} {l.uom}
                    </td>
                    <td className="px-3 py-2 text-right">{fmt(l.rate)}</td>
                    <td className="px-3 py-2 text-right">{fmt(l.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3} className="px-3 py-1.5 text-right text-[var(--sd-muted)]">
                    Tax: {preview.tax_label}
                  </td>
                  <td className="px-3 py-1.5 text-right">{fmt(preview.taxes.reduce((a, x) => a + x.amount, 0))}</td>
                </tr>
                <tr className="font-medium">
                  <td colSpan={3} className="px-3 py-2 text-right">
                    Total ({t.currency})
                  </td>
                  <td className="px-3 py-2 text-right">{fmt(preview.grand_total)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <dl className="grid gap-x-6 gap-y-1 text-[12px] text-[var(--sd-muted)] sm:grid-cols-2">
            <Detail label="Company" value={t.company} />
            <Detail label="Due" value={t.due_date} />
            <Detail label="Debit to" value={t.debit_to} />
            <Detail label="Cost centre" value={t.cost_center} />
            <Detail label="Farm" value={t.farm} />
            <Detail label="Business unit" value={t.business_unit} />
            <Detail label="Payment type (eTIMS)" value={t.payment_type_code} />
            <Detail label="Price list" value={t.price_list} />
          </dl>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-2">
      <dt className="shrink-0 text-[var(--sd-muted)]">{label}</dt>
      <dd className="min-w-0 truncate text-[var(--sd-ink)]">{value || "—"}</dd>
    </div>
  );
}
