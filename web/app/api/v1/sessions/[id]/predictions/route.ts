/**
 * GET  /api/v1/sessions/:id/predictions — list stored model outputs.
 * POST /api/v1/sessions/:id/predictions — run a model and store its output.
 *
 * Only one placeholder model exists: `cohort_zscore_v0` = how many SDs each
 * summary measurement is from this study's control participants. It is a
 * plumbing/exploration tool, NOT a Parkinson's classifier. A real model
 * (e.g. a Python service) would POST its output here in the same shape.
 */
import { NextResponse } from "next/server";
import { z } from "zod";
import { pgError, zodError } from "@/lib/http";
import { userClient } from "@/lib/supabase/server";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const sb = await userClient();
  const { data, error } = await sb.from("predictions").select("*").eq("session_id", id)
    .order("created_at", { ascending: false });
  if (error) return pgError(error);
  return NextResponse.json({ predictions: data });
}

const Body = z.union([
  z.object({ model: z.literal("cohort_zscore_v0") }),
  z.object({ model: z.literal("external"), model_name: z.string().min(1).max(64),
             model_version: z.string().min(1).max(32), output: z.record(z.unknown()) }),
]);

export async function POST(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const p = Body.safeParse(await req.json().catch(() => null));
  if (!p.success) return zodError(p.error);
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  const { data: sess, error: e0 } = await sb.from("assessment_sessions").select("study_id").eq("id", id).maybeSingle();
  if (e0) return pgError(e0);
  if (!sess) return NextResponse.json({ error: "session not found" }, { status: 404 });

  let row: { model_name: string; model_version: string; output: Record<string, unknown> };
  if (p.data.model === "cohort_zscore_v0") {
    const { data, error } = await sb.rpc("cohort_zscores", { p_session_id: id });
    if (error) return pgError(error);
    row = { model_name: "cohort_zscore", model_version: "0", output: {
      zscores: data, disclaimer: "Research-only comparison with this study's controls. Not a diagnosis." } };
  } else {
    row = { model_name: p.data.model_name, model_version: p.data.model_version, output: p.data.output };
  }
  const { data, error } = await sb.from("predictions")
    .insert({ session_id: id, study_id: sess.study_id, ...row }).select("*").single();
  if (error) return pgError(error);
  return NextResponse.json(data, { status: 201 });
}
