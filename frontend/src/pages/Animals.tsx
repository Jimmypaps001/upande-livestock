import { useCallback, useEffect, useState } from "react";
import { BarChart3, CalendarClock, ChevronLeft, ShieldAlert } from "lucide-react";
import { CompareDialog } from "@/components/animals/CompareDialog";
import { AnimalPortrait } from "@/components/animals/AnimalPortrait";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { CycleRing } from "@/components/animals/CycleRing";
import { EventFeed } from "@/components/animals/EventFeed";
import { KpiRadar } from "@/components/animals/KpiRadar";
import { LifeTimeline } from "@/components/animals/LifeTimeline";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import {
  benchmarkAxes,
  getAnimalProfile,
  getAnimals,
  getHerdBenchmarks,
  markCullReview,
  type HerdBenchmarks,
} from "@/lib/animals-api";
import { isError } from "@/lib/frappe";
import { ageFrom, type AnimalProfile, type AnimalSummary } from "@/lib/animals";
import { Button } from "@/components/ui/button";

/**
 * One animal, whole.
 *
 * The farm knows a cow by her number and by her story — five calvings, one
 * abortion, the mastitis in the spring — and that story is spread across four
 * doctypes and a dozen screens. This page is the one place it is assembled.
 *
 * The shape is a search beside a record: the list never goes away, because
 * looking one cow up almost always means looking the next one up straight
 * after, and a page that made you navigate back to search would charge for
 * that every time.
 *
 * The right rail is who she is — her photograph, and the six-axis shape of how
 * she has performed. The middle is what has happened to her. The division is
 * deliberate: identity does not scroll, history does.
 *
 * TWO CALLS, NOT ONE. The search list is redrawn as somebody types; the profile
 * walks an animal's whole event history. Asking for both together would make
 * the page as slow as its slowest cow. Profiles are cached as they arrive, so
 * looking one cow up and then comparing her with two others is three trips,
 * not three every time the dialog re-renders.
 */
export function Animals() {
  const [herd, setHerd] = useState<AnimalSummary[]>([]);
  const [selected, setSelected] = useState<AnimalSummary | null>(null);
  const [profiles, setProfiles] = useState<Record<string, AnimalProfile>>({});
  const [comparing, setComparing] = useState(false);
  const [bench, setBench] = useState<HerdBenchmarks | null>(null);
  const [culled, setCulled] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);

  const profile = selected ? profiles[selected.id] ?? null : null;

  const fetchProfile = useCallback((id: string) => {
    setProfiles((have) => {
      if (have[id]) return have;
      void getAnimalProfile(id).then((r) => {
        if (!isError(r)) setProfiles((s) => ({ ...s, [id]: r }));
      });
      return have;
    });
  }, []);

  useEffect(() => {
    void getAnimals().then((r) => {
      if (isError(r)) {
        setFailure(r.error);
        return;
      }
      setHerd(r.animals);
      setSelected((current) => current ?? r.animals[0] ?? null);
    });
  }, []);

  useEffect(() => {
    if (selected) fetchProfile(selected.id);
  }, [selected, fetchProfile]);

  // The herd's own medians, which are real even while the profiles are not:
  // the comparison is the one thing on this page that would be a lie if it
  // used made-up averages.
  useEffect(() => {
    void getHerdBenchmarks().then((r) => {
      if (!isError(r)) setBench(r);
    });
  }, []);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Animals" title="Animals">
        Every animal on the farm, and everything the system holds about each one —
        her herd, her cycle, her calvings and the events behind them.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
        {/* ── who to look at ─────────────────────────────────────────── */}
        <aside
          className={cn2(
            "min-w-0 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)]",
            profile && "hidden xl:flex xl:flex-col",
          )}
        >
          {/* On a surface, like everything else on the page. Loose on the
              paper it read as chrome rather than content, and it is the one
              control the page is actually built around. */}
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardContent className="flex min-h-0 flex-col p-4">
              <AnimalSearch
                animals={herd}
                selectedId={profile?.id ?? null}
                onSelect={setSelected}
              />
            </CardContent>
          </Card>
        </aside>

        {/* ── the record ─────────────────────────────────────────────── */}
        {profile ? (
          <div className="flex min-w-0 flex-col gap-5">
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="flex items-center gap-1.5 self-start text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)] xl:hidden"
            >
              <ChevronLeft className="h-4 w-4" />
              All animals
            </button>

            <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,280px)]">
              {/* the story */}
              <div className="flex min-w-0 flex-col gap-5">
                <Card>
                  <CardHeaderRow>
                    <CardHeading>
                      <CardTitle>Where she is in the cycle</CardTitle>
                      <CardDescription>
                        The loop between one calving and the next, drawn to the length
                        each stage actually takes.
                      </CardDescription>
                    </CardHeading>
                    {profile.cycle.nextOn && (
                      <span className="inline-flex shrink-0 items-center gap-2 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-3 py-1.5 text-[12px] text-[var(--sd-muted)]">
                        <CalendarClock className="h-3.5 w-3.5 text-[var(--sd-quiet)]" />
                        {profile.cycle.nextUp}
                        <span className="tabular-nums text-[var(--sd-ink)]">
                          {profile.cycle.nextOn}
                        </span>
                      </span>
                    )}
                  </CardHeaderRow>
                  <CardContent className="pt-0">
                    <CycleRing cycle={profile.cycle} />
                  </CardContent>
                </Card>

                <button
                  type="button"
                  onClick={() => setComparing(true)}
                  className="group w-full rounded-[var(--sd-radius-lg)] text-left transition-shadow hover:shadow-[var(--sd-shadow-2)]"
                  aria-label={`Compare ${profile.name} against the herd`}
                >
                <FigureRow>
                  <Figure
                    label="Calvings"
                    value={String(profile.kpis.parity)}
                    hint={profile.lastCalving ? `last ${profile.lastCalving}` : "none yet"}
                  />
                  <Figure
                    label="Carried to term"
                    value={
                      profile.kpis.conceptions
                        ? `${profile.kpis.conceptions - profile.kpis.abortions}/${profile.kpis.conceptions}`
                        : "—"
                    }
                    hint={`${profile.kpis.abortions} ${profile.kpis.abortions === 1 ? "abortion" : "abortions"}`}
                  />
                  <Figure
                    label="Conception rate"
                    value={profile.kpis.conceptionRate == null ? "—" : String(profile.kpis.conceptionRate)}
                    unit={profile.kpis.conceptionRate == null ? undefined : "%"}
                    hint={`${profile.kpis.services} ${profile.kpis.services === 1 ? "service" : "services"}`}
                  />
                  <Figure
                    label="Days in milk"
                    value={profile.cycle.daysInMilk == null ? "—" : String(profile.cycle.daysInMilk)}
                    hint={
                      profile.kpis.lactationYield
                        ? `${profile.kpis.lactationYield.toLocaleString()} kg this lactation`
                        : undefined
                    }
                  />
                </FigureRow>
                </button>

                <div className="-mt-2 flex flex-wrap items-center gap-3">
                  <Button variant="outline" size="sm" onClick={() => setComparing(true)}>
                    <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
                    Compare against the herd
                  </Button>
                  {culled[profile.id] && (
                    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--sd-sev-critical)]">
                      <ShieldAlert className="h-3.5 w-3.5" />
                      Marked for cull review
                    </span>
                  )}
                </div>

                <Card>
                  <CardHeaderRow>
                    <CardHeading>
                      <CardTitle>Her life so far</CardTitle>
                      <CardDescription>
                        {ageFrom(profile.bornOn)} on one line, to scale. The band underneath
                        is the herd she was standing in.
                      </CardDescription>
                    </CardHeading>
                  </CardHeaderRow>
                  <CardContent className="pt-0">
                    <LifeTimeline
                      bornOn={profile.bornOn}
                      milestones={profile.milestones}
                      spells={profile.spells}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeaderRow>
                    <CardHeading>
                      <CardTitle>Everything recorded</CardTitle>
                      <CardDescription>
                        Newest first, grouped by year.
                      </CardDescription>
                    </CardHeading>
                  </CardHeaderRow>
                  <CardContent className="pt-0">
                    <EventFeed milestones={profile.milestones} />
                  </CardContent>
                </Card>
              </div>

              {/* who she is — identity does not scroll */}
              <div className="flex min-w-0 flex-col gap-5 lg:sticky lg:top-6 lg:self-start">
                <AnimalPortrait animal={profile} />
                <Card>
                  <CardHeaderRow className="pb-0">
                    <CardHeading>
                      <CardTitle className="text-[14px]">How she compares</CardTitle>
                      <CardDescription>Outward is better on every axis.</CardDescription>
                    </CardHeading>
                  </CardHeaderRow>
                  <CardContent>
                    <KpiRadar kpis={profile.kpis} />
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        ) : (
          <Card className="hidden xl:block">
            <CardContent className="flex min-h-[420px] flex-col items-center justify-center gap-2 text-center">
              <p className="text-[15px] font-medium text-[var(--sd-ink)]">
                Pick an animal
              </p>
              <p className="max-w-[36ch] text-[13px] text-[var(--sd-muted)]">
                Search by register number, name or herd. Her cycle, her history and her
                figures open here.
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      {profile && (
        <CompareDialog
          open={comparing}
          onOpenChange={setComparing}
          subject={profile}
          herd={herd}
          profileFor={(a) => {
            fetchProfile(a.id);
            return profiles[a.id] ?? null;
          }}
          benchmark={benchmarkAxes(bench)}
          onMarkCull={async (reason) => {
            const r = await markCullReview(profile.id, reason);
            if (!isError(r)) setCulled((c) => ({ ...c, [profile.id]: reason }));
          }}
        />
      )}
    </Page>
  );
}

/** Local alias so this file does not import cn just for two call sites. */
function cn2(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
