import { ProjectionBody } from "@/pages/Projection";
import { Page, PageHeading } from "@/components/PageShell";

/**
 * The farm at a glance.
 *
 * Today this hosts the feed projection — what it will take to keep the herds
 * fed — and leaves a slot above it for the beef figures (head count, average
 * weight and average daily gain per herd).
 */
export function Dashboard() {
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Dashboard" title="Dashboard">
        How the herds stand, and what it will take to keep them fed.
      </PageHeading>

      {/* beef: head count, average weight and ADG per herd (Task 7) */}

      <ProjectionBody />
    </Page>
  );
}
