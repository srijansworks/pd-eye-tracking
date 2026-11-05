/**
 * POST /api/v1/sessions — create an assessment session.
 *   * Device:  Authorization: Bearer dk_...  body {participant_code, protocol?}
 *   * Human:   signed-in cookie             body {participant_code, protocol?, study_id}
 * GET /api/v1/sessions?participant_id=&limit= — list sessions (signed-in, RLS-filtered)
 */
import { NextResponse } from "next/server";
import { z } from "zod";
import { CreateSession } from "@/lib/schema";
import { bearer, pgError, zodError } from "@/lib/http";
import { deviceClient, userClient } from "@/lib/supabase/server";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const key = bearer(req);

  if (key) {
    const p = CreateSession.safeParse(body);
    if (!p.success) return zodError(p.error);
    const { data, error } = await deviceClient().rpc("device_create_session", {
      p_device_key: key, p_participant_code: p.data.participant_code, p_protocol: p.data.protocol ?? null,
    });
    if (error) return pgError(error);
    return NextResponse.json({ session_id: data }, { status: 201 });
  }

  const p = CreateSession.extend({ study_id: z.string().uuid() }).safeParse(body);
  if (!p.success) return zodError(p.error);
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  const { data: part, error: e1 } = await sb.from("participants").select("id")
    .eq("study_id", p.data.study_id).eq("code", p.data.participant_code).maybeSingle();
  if (e1) return pgError(e1);
  if (!part) return NextResponse.json({ error: "participant not found" }, { status: 404 });
  const { data, error } = await sb.from("assessment_sessions")
    .insert({ study_id: p.data.study_id, participant_id: part.id, protocol: p.data.protocol ?? null })
    .select("id").single();
  if (error) return pgError(error);
  return NextResponse.json({ session_id: data.id }, { status: 201 });
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  let q = sb.from("session_overview").select("*").order("started_at", { ascending: false })
    .limit(Math.min(Number(url.searchParams.get("limit") ?? 100), 500));
  const pid = url.searchParams.get("participant_id");
  if (pid) q = q.eq("participant_id", pid);
  const { data, error } = await q;
  if (error) return pgError(error);
  return NextResponse.json({ sessions: data });
}
