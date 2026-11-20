import { useCallback, useEffect, useMemo, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { isError } from "@/lib/frappe";
import { getLossClaims, type ClaimRow } from "@/lib/losses";

const STATUSES = ["All", "Draft", "Recorded", "Under Assessment", "Approved", "Rejected", "Settled"] as const;

const money = (n: number | null | undefined) => (n == null ? "—" : Number(n).toLocaleString());

/**
 * Insurance claims raised by recorded losses, for Accounts: where each stands
 * and what it is holding up. The claims themselves are moved on in Upande Asset.
 */
export function Claims() {
  const [rows, setRows] = useState<ClaimRow[] | null>(null);
  const [requirement, setRequirement] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("All");

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getLossClaims();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setRows(r.claims);
    setRequirement(r.requirement);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(
    () => (rows ?? []).filter((r) => status === "All" || r.claim_status === status),
    [rows, status],
  );

  return (
    <Page>
      <PageHeading
        eyebrow="Upande Livestock · Accounts"
        title="Insurance claims"
        actions={<RefreshButton onClick={load} loading={loading} label="the claims" />}
      >
        Claims raised by animal losses.{requirement ? ` Sales of insured animals wait for: ${requirement.toLowerCase()}.` : ""}
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Claim status">
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
            className={
              "rounded-full border px-3 py-1 text-[12px] " +
              (status === s ? "border-[var(--sd-ink)] bg-[var(--sd-card)] font-medium" : "border-[var(--sd-line)]")
            }
          >
            {s}
          </button>
        ))}
      </div>
      {rows && shown.length === 0 && <p className="text-[13px] text-[var(--sd-muted)]">No claims to show.</p>}
      {shown.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="text-[var(--sd-muted)]">
              <tr>
                {["Claim", "Animal", "Scenario", "Incident", "Status", "Claimed", "Approved", "Received", "Loss", "Papers missing"].map((h) => (
                  <th key={h} className="px-2 py-1.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.name} className="border-t border-[var(--sd-line)]">
                  <td className="px-2 py-1.5">
                    <a className="underline" href={`/app/insurance-claim/${encodeURIComponent(r.claim)}`}>
                      {r.claim}
                    </a>
                  </td>
                  <td className="px-2 py-1.5">{r.animal_name || r.animal}</td>
                  <td className="px-2 py-1.5">{r.scenario}</td>
                  <td className="px-2 py-1.5">{r.incident_date}</td>
                  <td className="px-2 py-1.5">{r.claim_status}</td>
                  <td className="px-2 py-1.5">{money(r.amount_claimed)}</td>
                  <td className="px-2 py-1.5">{money(r.amount_approved)}</td>
                  <td className="px-2 py-1.5">{money(r.amount_received)}</td>
                  <td className="px-2 py-1.5">{r.status}</td>
                  <td className="px-2 py-1.5">{r.missing_documents || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}
