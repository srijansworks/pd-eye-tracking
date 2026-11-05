import type { SupabaseClient } from "@supabase/supabase-js";

/** Everything the dashboard/API needs about one session. RLS applies. */
export async function sessionSummary(sb: SupabaseClient, sessionId: string) {
  const [ov, recs, ms, preds] = await Promise.all([
    sb.from("session_overview").select("*").eq("session_id", sessionId).maybeSingle(),
    sb.from("recordings")
      .select("id, modality, started_at, ended_at, sample_rate_hz, protocol, is_synthetic, clock_offset_ms, device_info, quality")
      .eq("session_id", sessionId).order("started_at"),
    sb.from("measurements")
      .select("recording_id, modality, name, value, unit, task, confidence, quality_flags, t")
      .eq("session_id", sessionId).is("t", null).order("modality").order("name"),
    sb.from("predictions").select("id, model_name, model_version, output, created_at")
      .eq("session_id", sessionId).order("created_at", { ascending: false }),
  ]);
  const error = ov.error ?? recs.error ?? ms.error ?? preds.error;
  return {
    error,
    session: ov.data,
    recordings: recs.data ?? [],
    measurements: ms.data ?? [],
    predictions: preds.data ?? [],
  };
}
