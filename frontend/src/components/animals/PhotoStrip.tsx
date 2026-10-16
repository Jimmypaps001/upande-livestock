import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ChevronLeft, ChevronRight } from "lucide-react";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { isError } from "@/lib/frappe";
import { addPhoto, getGallery, type AnimalPhoto } from "@/lib/photos";

/**
 * Her portfolio as a strip: every picture linked to her, newest first, with the
 * date and what it is of. `only` narrows it to one health case, and `upload`
 * adds a picture for that purpose; the server refuses a closed or foreign case,
 * so the button is only a convenience while a case is open.
 */
export function PhotoStrip({
  animal,
  only,
  upload,
  title = "Photos",
  empty = "No photos yet.",
}: {
  animal: string;
  /** Show only pictures attached to this document (a health case). */
  only?: string;
  upload?: { context: "health_case" | "birth" | "profile"; ref?: string; label?: string };
  title?: string;
  empty?: string;
}) {
  const [photos, setPhotos] = useState<AnimalPhoto[] | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const load = useCallback(async () => {
    const r = await getGallery(animal);
    if (isError(r)) {
      setPhotos([]);
      return;
    }
    const all = r.photos ?? [];
    setPhotos(only ? all.filter((p) => p.ref_name === only) : all);
  }, [animal, only]);

  useEffect(() => {
    setPhotos(null);
    void load();
  }, [load]);

  async function chosen(file: File | undefined) {
    if (!file || !upload) return;
    setBusy(true);
    const r = await addPhoto({ animal, file, context: upload.context, ref: upload.ref });
    setBusy(false);
    if (input.current) input.current.value = "";
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast("Photo added.");
    void load();
  }

  const shown = photos ?? [];
  const p = viewing !== null ? shown[viewing] : null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10.5px] font-medium uppercase tracking-[0.13em] text-[var(--sd-quiet)]">
          {title}
          {shown.length ? ` · ${shown.length}` : ""}
        </p>
        {upload && (
          <>
            <input
              ref={input}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              aria-label="Choose a photo"
              onChange={(e) => void chosen(e.target.files?.[0])}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              <Camera className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
              {busy ? "Uploading…" : (upload.label ?? "Add photo")}
            </Button>
          </>
        )}
      </div>

      {photos && !shown.length && <p className="text-[12px] text-[var(--sd-quiet)]">{empty}</p>}

      {!!shown.length && (
        <ul className="flex gap-2.5 overflow-x-auto pb-1">
          {shown.map((ph, i) => (
            <li key={`${ph.url}-${i}`} className="shrink-0">
              <button
                type="button"
                onClick={() => setViewing(i)}
                aria-label={`${ph.source} photo, ${ph.date.slice(0, 10)}`}
                className="relative block h-24 w-24 overflow-hidden rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)]"
              >
                <img src={ph.thumb || ph.url} alt="" loading="lazy" className="h-full w-full object-cover" />
                <span className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 text-[10px] font-medium text-white">
                  {ph.source}
                </span>
              </button>
              <p className="mt-1 text-[10.5px] tabular-nums text-[var(--sd-quiet)]">
                {ph.date.slice(0, 10)}
              </p>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={p !== null} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent className="max-w-3xl">
          {p && (
            <div className="flex flex-col gap-3">
              <DialogTitle>{p.caption || `${p.source} photo`}</DialogTitle>
              <DialogDescription>
                {p.source} · {p.date.slice(0, 10)}
                {p.uploaded_by ? ` · ${p.uploaded_by}` : ""}
                {p.ref_doctype !== "Animal" ? ` · ${p.ref_name}` : ""}
              </DialogDescription>
              <img src={p.url} alt={p.caption || p.source} className="max-h-[70vh] w-full object-contain" />
              {shown.length > 1 && (
                <div className="flex justify-between">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setViewing((i) => ((i ?? 0) - 1 + shown.length) % shown.length)}
                  >
                    <ChevronLeft className="h-4 w-4" /> Newer
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setViewing((i) => ((i ?? 0) + 1) % shown.length)}
                  >
                    Older <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
