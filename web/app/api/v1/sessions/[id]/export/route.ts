/** GET /api/v1/sessions/:id/export — all measurements of a session as CSV. */
import { NextResponse } from "next/server";
import { pgError } from "@/lib/http";
import { userClient } from "@/lib/supabase/server";

const esc = (v: unknown) => {
  const s = v == null ? "" : Array.isArray(v) ? v.join(";") : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const sb = await userClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  const { data, error } = await sb.from("measurements")
    .select("modality, name, value, unit, task, confidence, quality_flags, t, recording_id")
    .eq("session_id", id).order("modality").order("name");
  if (error) return pgError(error);
  const cols = ["modality", "name", "value", "unit", "task", "confidence", "quality_flags", "t", "recording_id"] as const;
  const csv = [cols.join(","), ...(data ?? []).map((r: any) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  return new NextResponse(csv, {
    headers: { "content-type": "text/csv", "content-disposition": `attachment; filename="session-${id}.csv"` },
  });
}
