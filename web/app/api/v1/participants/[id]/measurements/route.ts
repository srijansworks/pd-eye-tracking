/**
 * GET /api/v1/participants/:id/measurements?name=saccade_latency_median&modality=eye
 * History of summary measurements across all of a participant's sessions (for trends).
 */
import { NextResponse } from "next/server";
import { pgError } from "@/lib/http";
import { userClient } from "@/lib/supabase/server";

export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const url = new URL(req.url);
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  const { data: sessions, error: e1 } = await sb.from("assessment_sessions")
    .select("id, started_at").eq("participant_id", id).order("started_at");
  if (e1) return pgError(e1);
  if (!sessions?.length) return NextResponse.json({ series: {} });

  let q = sb.from("measurements").select("session_id, modality, name, value, unit, confidence, quality_flags")
    .in("session_id", sessions.map((s) => s.id)).is("t", null);
  const name = url.searchParams.get("name");
  const modality = url.searchParams.get("modality");
  if (name) q = q.eq("name", name);
  if (modality) q = q.eq("modality", modality);
  const { data, error } = await q;
  if (error) return pgError(error);

  const when = new Map(sessions.map((s) => [s.id, s.started_at]));
  const series: Record<string, { started_at: string; session_id: string; value: number; unit: string; confidence: number | null }[]> = {};
  for (const m of data ?? []) {
    (series[m.name] ??= []).push({ started_at: when.get(m.session_id)!, session_id: m.session_id,
                                   value: m.value, unit: m.unit, confidence: m.confidence });
  }
  for (const k in series) series[k].sort((a, b) => a.started_at.localeCompare(b.started_at));
  return NextResponse.json({ series });
}
