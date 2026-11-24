"use client";

import { type RefObject, useState } from "react";
import { api } from "@/lib/api";
import type { Job, TrollKind, TrollRequest } from "@/lib/types";
import { useCapability, useJobRunner } from "./studio";
import { planSteps, type RemixChanges, type StepId } from "./troll";

/** Generate, regenerate and remix trolls on one page, following the job with a step timeline. */
export function useTrollSession(anchor: RefObject<HTMLDivElement | null>) {
  const runner = useJobRunner();
  const [steps, setSteps] = useState<StepId[]>([]);
  const [result, setResult] = useState<Job | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [kind, setKind] = useState<TrollKind>("diss_track");
  const sung = !!useCapability("music").capability?.sings;

  function start() {
    setResult(null);
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function generate(request: TrollRequest, opts: { video?: boolean; sameProject?: boolean } = {}) {
    setKind(request.kind);
    setSteps(planSteps(request.kind, { video: opts.video, sung }));
    start();
    const done = await runner.run(() => api.troll(request, opts.sameProject ? project : null, { with_video: !!opts.video }));
    if (done) {
      setResult(done);
      setProject(done.project_id);
    }
  }

  async function remix(assetId: string, changes: RemixChanges, trollKind: TrollKind = kind) {
    const rewrite = !!(changes.instruction || changes.delivery || changes.intensity || changes.regenerate_sections?.length);
    setSteps(planSteps(trollKind, { reuseLyrics: trollKind !== "funny_beat", rewrite, sung }));
    start();
    const done = await runner.run(() => api.remix({ asset_id: assetId, ...changes }));
    if (done) setResult(done);
  }

  function retried(done: Job) {
    setResult(done);
    setProject(done.project_id);
  }

  return { runner, steps, result, project, generate, remix, retried };
}
