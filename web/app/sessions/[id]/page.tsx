import { notFound } from "next/navigation";
import { sessionSummary } from "@/lib/queries";
import { userClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await sessionSummary(await userClient(), id);
  if (s.error) return <p>Error: {s.error.message}</p>;
  if (!s.session) notFound();
  const sess: any = s.session;

  return (
    <>
      <h2>Session · {sess.participant_code} · {new Date(sess.started_at).toLocaleString()}</h2>
      <p className="muted">
        Protocol {sess.protocol ?? "—"} · status {sess.status} ·{" "}
        <a href={`/api/v1/sessions/${id}/export`}>download CSV</a> ·{" "}
        <a href={`/api/v1/sessions/${id}`}>JSON</a>
      </p>

      <h3>Recordings</h3>
      <table>
        <thead><tr><th>Sensor</th><th>Started</th><th className="num">Rate</th><th className="num">Clock offset</th><th>Quality flags</th></tr></thead>
        <tbody>
          {s.recordings.map((r: any) => (
            <tr key={r.id}>
              <td>{r.modality}{r.is_synthetic && <span className="flag">synthetic</span>}</td>
              <td>{new Date(r.started_at).toLocaleTimeString()}</td>
              <td className="num">{r.sample_rate_hz ? `${Number(r.sample_rate_hz).toFixed(1)} Hz` : "—"}</td>
              <td className="num">{r.clock_offset_ms} ms</td>
              <td>{(r.quality?.flags ?? []).map((f: string) => <span key={f} className="flag">{f}</span>)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Measurements</h3>
      <table>
        <thead><tr><th>Sensor</th><th>Task</th><th>Name</th><th className="num">Value</th><th>Unit</th><th className="num">Confidence</th><th>Flags</th></tr></thead>
        <tbody>
          {s.measurements.map((m: any, i: number) => (
            <tr key={i} style={{ opacity: m.confidence != null && m.confidence < 0.3 ? 0.55 : 1 }}>
              <td>{m.modality}</td><td>{m.task}</td><td>{m.name}</td>
              <td className="num">{Number(m.value).toPrecision(4)}</td><td>{m.unit}</td>
              <td className="num">{m.confidence ?? "—"}</td>
              <td>{(m.quality_flags ?? []).map((f: string) => <span key={f} className="flag">{f}</span>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Faded rows have confidence &lt; 0.3 (e.g. peak velocity from a 30 fps camera).</p>

      {s.predictions.length > 0 && (<>
        <h3>Model outputs (research only)</h3>
        <pre style={{ background: "#fff", padding: 12, fontSize: 12 }}>{JSON.stringify(s.predictions, null, 2)}</pre>
      </>)}
    </>
  );
}
