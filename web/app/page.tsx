import { userClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function Home() {
  const sb = await userClient();
  const { data: sessions, error } = await sb.from("session_overview").select("*")
    .order("started_at", { ascending: false }).limit(200);
  if (error) return <p>Error: {error.message}</p>;

  return (
    <>
      <div className="banner">
        Values are webcam-grade research measurements with quality flags. They are not validated
        for diagnosing or screening Parkinson&apos;s disease.
      </div>
      <table>
        <thead>
          <tr><th>Started</th><th>Participant</th><th>Cohort</th><th>Protocol</th><th>Sensors</th>
            <th className="num">Measurements</th><th className="num">Eye valid frames</th><th /></tr>
        </thead>
        <tbody>
          {(sessions ?? []).map((s: any) => (
            <tr key={s.session_id}>
              <td>{new Date(s.started_at).toLocaleString()}</td>
              <td><a href={`/participants/${s.participant_id}`}>{s.participant_code}</a>{s.is_synthetic && <span className="flag">synthetic</span>}</td>
              <td>{s.cohort}</td>
              <td>{s.protocol ?? "—"}</td>
              <td>{(s.modalities ?? []).join(", ") || "—"}</td>
              <td className="num">{s.n_measurements}</td>
              <td className="num">{s.eye_valid_frame_fraction != null ? `${(s.eye_valid_frame_fraction * 100).toFixed(0)}%` : "—"}</td>
              <td><a href={`/sessions/${s.session_id}`}>open</a></td>
            </tr>
          ))}
          {!sessions?.length && <tr><td colSpan={8} className="muted">No sessions yet — run <code>eyetrack upload</code>.</td></tr>}
        </tbody>
      </table>
    </>
  );
}
