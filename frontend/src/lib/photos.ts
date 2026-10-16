/**
 * An animal's portfolio, off the server. The page uploads the picture and
 * names what it is for; whether a case is hers and still open is the server's.
 */
import { call, uploadFile, type Envelope } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.animals.animal_photos";

export type PhotoSource = "Profile" | "Birth" | "Health case" | "Event";

export interface AnimalPhoto {
  name: string | null;
  url: string;
  thumb: string | null;
  date: string;
  source: PhotoSource;
  ref_doctype: string;
  ref_name: string;
  caption: string;
  uploaded_by: string;
}

export const getGallery = (animal: string) =>
  call<{ photos: AnimalPhoto[] }>(`${NS}.animal_gallery`, { animal });

export async function addPhoto(input: {
  animal: string;
  file: File;
  context: "health_case" | "birth" | "profile";
  ref?: string;
  caption?: string;
}): Promise<Envelope<{ url: string }>> {
  const up = await uploadFile(input.file);
  if ("error" in up) return up;
  return call<{ url: string }>(`${NS}.add_animal_photo`, {
    animal: input.animal,
    file_url: up.file_url,
    context: input.context,
    ref: input.ref,
    caption: input.caption,
  });
}
