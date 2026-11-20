import { Lock } from "lucide-react";
import { Page, PageHeading } from "@/components/PageShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Shown when a direct URL names a page the user's roles do not reach and there
 * is nowhere better to send them. Everywhere else the route redirects home.
 */
export function NotAvailable({ title }: { title: string }) {
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock" title={title} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-[15px]">
            <Lock className="h-4 w-4 text-[var(--sd-quiet)]" />
            Not available for your role
          </CardTitle>
          <CardDescription>
            This page is not part of the work your role does here. If you need it, ask a
            Livestock Manager to change your access.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <a href="/app" className="text-[13px] font-medium text-[var(--sd-ink)] underline underline-offset-4">
            Back to Desk
          </a>
        </CardContent>
      </Card>
    </Page>
  );
}
