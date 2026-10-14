import { useEffect, useState } from "react";
import { call, isError, type Envelope } from "@/lib/frappe";

const VET_OPTIONS = "upande_livestock.serverscripts.people.vet_options.vet_options";

export interface VetChoice {
  value: string;
  label: string;
  /** Internal (a farm employee) or External (a visiting practitioner). */
  type: "Internal" | "External";
  detail: string;
}

export interface VetOptions {
  vets: VetChoice[];
  /** The Livestock Vet record of whoever is signed in, or null. */
  mine: string | null;
}

/** Enabled vets, and the signed-in user's own. */
export function getVetOptions(): Promise<Envelope<VetOptions>> {
  return call<VetOptions>(VET_OPTIONS, { payload: {} });
}

/**
 * The vets a record may name. Loaded once per mount; the picker starts on the
 * signed-in user's own vet record when they have one, and the server applies the
 * same default when none is sent.
 */
export function useVets() {
  const [vets, setVets] = useState<VetChoice[]>([]);
  const [mine, setMine] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    void getVetOptions().then((r) => {
      if (!live) return;
      if (!isError(r)) {
        setVets(r.vets ?? []);
        setMine(r.mine ?? null);
      }
      setLoaded(true);
    });
    return () => {
      live = false;
    };
  }, []);

  return { vets, mine, loaded };
}

/** `useVets` plus the chosen vet, started on the signed-in user's own record
 *  and never overwritten once somebody has chosen. */
export function useVetChoice() {
  const { vets, mine, loaded } = useVets();
  // null until somebody chooses; "" is a deliberate "no vet".
  const [picked, setVet] = useState<string | null>(null);
  const vet = picked ?? mine ?? "";
  return { vets, vet, setVet, loaded };
}
