import { useCallback, useEffect, useState } from "react";
import { BandLadderEditor } from "@/components/herds/BandLadderEditor";
import { isError } from "@/lib/frappe";
import { getHerdRations, type HerdBand } from "@/lib/herds";

type Listed = Partial<HerdBand> & { herd: string };

/**
 * The feedlot weight bands (Starters, Growers, Finishers), editable where the
 * farm's other rules are. The numbers live on the Fattening herds, so this is
 * the same ladder editor the Herds page has, saving through the same endpoint:
 * one copy of the numbers, two doors to it.
 */
export function FeedlotBandsCard({ onSaved }: { onSaved?: (message: string) => void }) {
  const [bands, setBands] = useState<HerdBand[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getHerdRations();
    setLoading(false);
    // A failure here costs the editor, not the settings page.
    if (isError(r)) return;
    setBands(
      ((r as { herds?: Listed[] }).herds || []).map(
        (x) =>
          ({
            herd: x.herd,
            herd_class: x.herd_class || "Other",
            min_weight_kg: x.min_weight_kg ?? null,
            max_weight_kg: x.max_weight_kg ?? null,
            target_adg_kg: x.target_adg_kg ?? null,
            weigh_monthly: x.weigh_monthly ?? 0,
          }) as HerdBand,
      ),
    );
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <BandLadderEditor
      bands={bands}
      loading={loading}
      onDone={(m) => {
        onSaved?.(m);
        void load();
      }}
    />
  );
}
