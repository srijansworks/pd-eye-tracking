/** GET /api/v1/sessions/:id — session summary: overview, recordings (+quality), summary measurements, predictions. */
import { NextResponse } from "next/server";
import { pgError } from "@/lib/http";
import { sessionSummary } from "@/lib/queries";
import { userClient } from "@/lib/supabase/server";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  const s = await sessionSummary(sb, id);
  if (s.error) return pgError(s.error);
  if (!s.session) return NextResponse.json({ error: "session not found" }, { status: 404 });
  return NextResponse.json(s);
}
