import { userClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/** Tiny inline SVG trend line — no chart library needed for an MVP. */
function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="muted">1 point</span>;
  const w = 160, h = 32, lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - lo) / span) * (h - 4) - 2}`).join(" ");
  return <svg width={w} height={h}><polyline points={pts} fill="none" stroke="#0b5cff" strokeWidth={1.5} /></svg>;
}

export default async function ParticipantPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const sb = await userClient();
  const { data: p } = await sb.from("participants").select("code, cohort, is_synthetic").eq("id", id).maybeSingle();
  const { data: sessions } = await sb.from("assessment_sessions").select("id, started_at").eq("participant_id", id).order("started_at");
  const ids = (sessions ?? []).map((s) => s.id);
  const { data: ms } = ids.length
    ? await sb.from("measurements").select("session_id, modality, name, value, unit").in("session_id", ids).is("t", null)
    : { data: [] as any[] };

  const order = new Map(ids.map((sid, i) => [sid, i]));
  const series = new Map<string, { unit: string; pts: [number, number][] }>();
  for (const m of ms ?? []) {
    const k = `${m.modality} · ${m.name}`;
    if (!series.has(k)) series.set(k, { unit: m.unit, pts: [] });
    series.get(k)!.pts.push([order.get(m.session_id)!, m.value]);
  }

  return (
    <>
      <h2>Participant {p?.code} <span className="muted">({p?.cohort}{p?.is_synthetic ? ", synthetic" : ""})</span></h2>
      <p className="muted">{ids.length} session(s). Trends across sessions, oldest → newest.</p>
      <table>
        <thead><tr><th>Measurement</th><th>Trend</th><th className="num">Latest</th><th>Unit</th></tr></thead>
        <tbody>
          {[...series.entries()].sort().map(([k, s]) => {
            const vals = s.pts.sort((a, b) => a[0] - b[0]).map((x) => x[1]);
            return (
              <tr key={k}><td>{k}</td><td><Spark values={vals} /></td>
                <td className="num">{vals.at(-1)?.toPrecision(4)}</td><td>{s.unit}</td></tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
