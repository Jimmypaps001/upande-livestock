import { Construction } from "lucide-react";
import { Page, PageHeading } from "@/components/PageShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * A surface the sidebar names but this frontend does not implement yet.
 *
 * It says so plainly rather than rendering an empty table or a disabled form:
 * the desk block is still live and still does this work, and pointing the
 * operator there is more useful than a screen that looks broken.
 */
export function Stub({ title }: { title: string }) {
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock" title={title} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-[15px]">
            <Construction className="h-4 w-4 text-[var(--sd-quiet)]" />
            Not built here yet
          </CardTitle>
          <CardDescription>
            {title} still runs on the Livestock Operations block in the desk, which is
            live and unchanged. This page will take it over in a later slice.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <a
            href="/app/upande-livestock"
            className="text-[13px] font-medium text-[var(--sd-ink)] underline underline-offset-4"
          >
            Open the desk workspace
          </a>
        </CardContent>
      </Card>
    </Page>
  );
}
