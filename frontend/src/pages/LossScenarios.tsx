import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { ScenarioDialog } from "@/components/losses/ScenarioDialog";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import { isError } from "@/lib/frappe";
import { canEditScenarios, deleteLossScenario, getLossScenarios, type LossScenario } from "@/lib/losses";

/** Configuration ▸ Loss scenarios: the list, and a modal to add or change one. */
export function LossScenarios() {
  const [rows, setRows] = useState<LossScenario[] | null>(null);
  const [types, setTypes] = useState<string[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<LossScenario | null>(null);
  const [adding, setAdding] = useState(false);
  const mayEdit = canEditScenarios();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getLossScenarios(true);
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setRows(r.scenarios);
    setTypes(r.incident_types);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(s: LossScenario) {
    const r = await deleteLossScenario(s.name);
    if (isError(r)) setFailure(r.error);
    else void load();
  }

  return (
    <Page>
      <PageHeading
        eyebrow="Upande Livestock · Configuration"
        title="Loss scenarios"
        actions={
          <>
            <RefreshButton onClick={load} loading={loading} label="the scenarios" />
            {mayEdit && (
              <Button onClick={() => setAdding(true)}>
                <Plus className="mr-1.5 h-4 w-4" />
                Add scenario
              </Button>
            )}
          </>
        }
      >
        What each kind of loss means: whether to claim, the papers needed, and where the animal goes.
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}
      {rows && rows.length === 0 && <p className="text-[13px] text-[var(--sd-muted)]">No scenarios yet.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="text-[var(--sd-muted)]">
              <tr>
                {["Scenario", "Trigger", "Outcome", "Claim", "Papers", "Active", ""].map((h) => (
                  <th key={h} className="px-2 py-1.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.name} className="border-t border-[var(--sd-line)]">
                  <td className="px-2 py-1.5 font-medium">{s.scenario_name}</td>
                  <td className="px-2 py-1.5">{s.trigger}</td>
                  <td className="px-2 py-1.5">{s.outcome}</td>
                  <td className="px-2 py-1.5">{s.claim_insurance ? `${s.incident_type ?? ""} · ${s.loss_treatment ?? ""}` : "No"}</td>
                  <td className="px-2 py-1.5">{s.required_documents.map((d) => d.document_name).join(", ") || "—"}</td>
                  <td className="px-2 py-1.5">{s.active ? "Yes" : "No"}</td>
                  <td className="px-2 py-1.5 text-right">
                    {mayEdit && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => setEditing(s)}>
                          Edit
                        </Button>{" "}
                        <Button size="sm" variant="outline" onClick={() => void remove(s)}>
                          Delete
                        </Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ScenarioDialog
        open={adding || editing !== null}
        onOpenChange={(o) => {
          if (!o) {
            setAdding(false);
            setEditing(null);
          }
        }}
        scenario={editing}
        incidentTypes={types}
        onSaved={() => void load()}
      />
    </Page>
  );
}
