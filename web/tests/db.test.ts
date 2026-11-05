/**
 * Database tests: run the real Supabase migrations inside PGlite (Postgres
 * compiled to WebAssembly) — no Docker, no Supabase account needed.
 * RLS is tested by switching to the `authenticated` / `anon` roles exactly
 * as PostgREST does.
 */
import type { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { ROOT, as as asDb, makeDb } from "./helpers/db";

const EXAMPLE = JSON.parse(readFileSync(join(ROOT, "docs/examples/eye-batch.example.json"), "utf8"));

const A = "aaaaaaaa-0000-4000-8000-000000000001"; // researcher A (study owner)
const B = "bbbbbbbb-0000-4000-8000-000000000002"; // unrelated user B
const V = "cccccccc-0000-4000-8000-000000000003"; // viewer in A's study

let db: PGlite;
const as = <T = any>(who: string | null, sql: string, params: any[] = []) => asDb<T>(db, who, sql, params);

let studyA: string, studyB: string, partA: string, sessA: string, sessB: string;
let eyeKey: string, wristKey: string, keyB: string;

function batch(sessionId: string, overrides: Record<string, any> = {}) {
  return { ...structuredClone(EXAMPLE), session_id: sessionId, ...overrides };
}

beforeAll(async () => {
  db = await makeDb();
  await db.query("insert into auth.users (id, email) values ($1,'a@x.test'),($2,'b@x.test'),($3,'v@x.test')", [A, B, V]);

  studyA = (await as<any>(A, "insert into studies (name) values ('Study A') returning id"))[0].id;
  studyB = (await as<any>(B, "insert into studies (name) values ('Study B') returning id"))[0].id;
  await as(A, "insert into study_members (study_id, user_id, role) values ($1, $2, 'viewer')", [studyA, V]);

  partA = (await as<any>(A, "insert into participants (study_id, code, cohort, is_synthetic) values ($1,'SYN-001','synthetic',true) returning id", [studyA]))[0].id;
  const partB = (await as<any>(B, "insert into participants (study_id, code) values ($1,'P-B1') returning id", [studyB]))[0].id;
  sessA = (await as<any>(A, "insert into assessment_sessions (study_id, participant_id, protocol) values ($1,$2,'eye_v1') returning id", [studyA, partA]))[0].id;
  sessB = (await as<any>(B, "insert into assessment_sessions (study_id, participant_id) values ($1,$2) returning id", [studyB, partB]))[0].id;

  eyeKey = (await as<any>(A, "select * from create_device($1,'laptop','eye')", [studyA]))[0].device_key;
  wristKey = (await as<any>(A, "select * from create_device($1,'wrist hub','wrist')", [studyA]))[0].device_key;
  keyB = (await as<any>(B, "select * from create_device($1,'B cam','eye')", [studyB]))[0].device_key;
});

describe("schema + ownership", () => {
  it("auto-adds study creator as owner and creates profiles", async () => {
    const m = await as<any>(A, "select role from study_members where study_id = $1 and user_id = $2", [studyA, A]);
    expect(m[0].role).toBe("owner");
    expect((await db.query<any>("select count(*)::int n from profiles")).rows[0].n).toBe(3);
  });

  it("stores only a hash of device keys", async () => {
    expect(eyeKey).toMatch(/^dk_[0-9a-f]{64}$/);
    const rows = (await db.query<any>("select key_prefix, encode(key_hash,'hex') h from devices")).rows;
    expect(rows.some((r: any) => r.h.includes(eyeKey.slice(3)))).toBe(false);
  });

  it("rejects participant codes that look like names", async () => {
    await expect(as(A, "insert into participants (study_id, code) values ($1, 'Jane Doe')", [studyA])).rejects.toThrow(/check/);
  });

  it("cannot attach a session to a participant from another study", async () => {
    await expect(as(A, "insert into assessment_sessions (study_id, participant_id) values ($1, $2)", [studyB, partA]))
      .rejects.toThrow();
  });
});

describe("row level security", () => {
  it("users only see their own studies' data", async () => {
    expect(await as(B, "select * from participants where study_id = $1", [studyA])).toHaveLength(0);
    expect(await as(B, "select * from studies where id = $1", [studyA])).toHaveLength(0);
    expect(await as(A, "select * from participants where study_id = $1", [studyA])).toHaveLength(1);
  });

  it("anon cannot read tables directly", async () => {
    await expect(as(null, "select * from measurements")).rejects.toThrow(/permission denied/);
    await expect(as(null, "select * from devices")).rejects.toThrow(/permission denied/);
  });

  it("viewers can read but not write", async () => {
    expect(await as(V, "select * from participants where study_id = $1", [studyA])).toHaveLength(1);
    await expect(as(V, "insert into participants (study_id, code) values ($1,'SYN-002')", [studyA])).rejects.toThrow(/row-level security/);
    await expect(as(V, "select * from create_device($1,'x','eye')", [studyA])).rejects.toThrow(/not a researcher/);
  });

  it("B cannot create devices in A's study", async () => {
    await expect(as(B, "select * from create_device($1,'evil','eye')", [studyA])).rejects.toThrow(/not a researcher/);
  });
});

describe("device ingest", () => {
  it("anon device can create a session by participant code", async () => {
    const r = await as<any>(null, "select device_create_session($1,'SYN-001','eye_v1') sid", [eyeKey]);
    expect(r[0].sid).toMatch(/[0-9a-f-]{36}/);
    await expect(as(null, "select device_create_session($1,'NOPE')", [eyeKey])).rejects.toThrow(/unknown participant/);
  });

  it("ingests the real Python batch atomically, and is idempotent", async () => {
    const r = (await as<any>(null, "select ingest_batch($1, $2::jsonb) r", [eyeKey, JSON.stringify(batch(sessA))]))[0].r;
    expect(r.duplicate).toBe(false);
    expect(r.n_measurements).toBe(EXAMPLE.measurements.length);
    expect(r.n_events).toBe(EXAMPLE.events.length);
    const again = (await as<any>(null, "select ingest_batch($1, $2::jsonb) r", [eyeKey, JSON.stringify(batch(sessA))]))[0].r;
    expect(again).toEqual({ recording_id: r.recording_id, duplicate: true });
    const n = await as<any>(A, "select count(*)::int n from measurements where session_id = $1", [sessA]);
    expect(n[0].n).toBe(EXAMPLE.measurements.length);
    expect(await as(B, "select * from measurements where session_id = $1", [sessA])).toHaveLength(0);
  });

  it("rejects bad keys, wrong modality, foreign sessions, raw media", async () => {
    await expect(as(null, "select ingest_batch('dk_wrong', $1::jsonb)", [JSON.stringify(batch(sessA))])).rejects.toThrow(/invalid or revoked/);
    await expect(as(null, "select ingest_batch($1, $2::jsonb)", [wristKey, JSON.stringify(batch(sessA))])).rejects.toThrow(/cannot upload eye/);
    await expect(as(null, "select ingest_batch($1, $2::jsonb)", [keyB, JSON.stringify(batch(sessA))])).rejects.toThrow(/session not found/);
    const raw = batch(sessA); raw.recording = { ...raw.recording, raw_media_stored: true, started_at: "2026-11-04T19:00:00Z" };
    await expect(as(null, "select ingest_batch($1, $2::jsonb)", [eyeKey, JSON.stringify(raw)])).rejects.toThrow(/raw media/);
    // atomic: a bad measurement name rolls back the whole batch
    const bad = batch(sessA); bad.recording = { ...bad.recording, started_at: "2026-11-04T20:00:00Z" };
    bad.measurements = [...bad.measurements, { name: "Bad Name", value: 1, unit: "x" }];
    await expect(as(null, "select ingest_batch($1, $2::jsonb)", [eyeKey, JSON.stringify(bad)])).rejects.toThrow();
    const recs = await as<any>(A, "select count(*)::int n from recordings where session_id = $1", [sessA]);
    expect(recs[0].n).toBe(1);
  });

  it("a wrist device can add its own recording to the same session", async () => {
    const wrist = {
      schema_version: "1.0", session_id: sessA,
      recording: { modality: "wrist", started_at: "2026-11-04T18:00:01.250Z", sample_rate_hz: 100,
                   clock: { source: "ble_host", offset_ms: -42 } },
      measurements: [{ name: "tremor_peak_frequency", value: 5.1, unit: "Hz", task: "rest", confidence: 0.8 }],
      events: [{ t: "2026-11-04T18:00:02.000Z", kind: "sync_tap" }],
    };
    const r = (await as<any>(null, "select ingest_batch($1, $2::jsonb) r", [wristKey, JSON.stringify(wrist)]))[0].r;
    expect(r.n_measurements).toBe(1);
    const ov = (await as<any>(A, "select * from session_overview where session_id = $1", [sessA]))[0];
    expect(ov.modalities.sort()).toEqual(["eye", "wrist"]);
    expect(Number(ov.n_recordings)).toBe(2);
    expect(await as(B, "select * from session_overview where session_id = $1", [sessA])).toHaveLength(0);
  });

  it("revoked keys stop working", async () => {
    const k = (await as<any>(A, "select * from create_device($1,'temp','eye')", [studyA]))[0];
    await as(A, "update devices set revoked_at = now() where id = $1", [k.device_id]);
    await expect(as(null, "select device_create_session($1,'SYN-001')", [k.device_key])).rejects.toThrow(/revoked/);
  });
});

describe("privacy + research guards", () => {
  it("raw media path requires active consent", async () => {
    const rid = (await as<any>(A, "select id from recordings where session_id = $1 and modality = 'eye'", [sessA]))[0].id;
    await expect(as(A, "update recordings set raw_media_path = 'x/y/z.mp4' where id = $1", [rid])).rejects.toThrow(/consent/);
    await as(A, "insert into consents (study_id, participant_id, kind) values ($1,$2,'raw_video_storage')", [studyA, partA]);
    await as(A, "update recordings set raw_media_path = 'x/y/z.mp4' where id = $1", [rid]);
  });

  it("storage policy: only researchers with consent can write raw media", async () => {
    const path = `${studyA}/${sessA}/video.mp4`;
    await as(A, "insert into storage.objects (bucket_id, name) values ('raw-media', $1)", [path]);
    await expect(as(V, "insert into storage.objects (bucket_id, name) values ('raw-media', $1)", [path])).rejects.toThrow(/row-level security/);
    await expect(as(B, "insert into storage.objects (bucket_id, name) values ('raw-media', $1)", [path])).rejects.toThrow(/row-level security/);
    await expect(as(B, "insert into storage.objects (bucket_id, name) values ('raw-media', $1)", [`${studyB}/${sessB}/v.mp4`])).rejects.toThrow(/row-level security/);
  });

  it("predictions must be flagged research-only", async () => {
    await expect(as(A, "insert into predictions (session_id, study_id, model_name, model_version, output, is_research_only) values ($1,$2,'m','0','{}',false)", [sessA, studyA])).rejects.toThrow(/check/);
  });

  it("cohort z-scores compare against >= 2 control participants", async () => {
    // add 3 synthetic controls with sessions + one measurement each
    for (const [i, v] of [[1, 190], [2, 210], [3, 200]] as const) {
      const p = (await as<any>(A, "insert into participants (study_id, code, cohort, is_synthetic) values ($1,$2,'control',true) returning id", [studyA, `CTL-${i}`]))[0].id;
      const s = (await as<any>(A, "insert into assessment_sessions (study_id, participant_id) values ($1,$2) returning id", [studyA, p]))[0].id;
      const r = (await as<any>(A, "insert into recordings (session_id, study_id, modality, started_at) values ($1,$2,'eye',now()) returning id", [s, studyA]))[0].id;
      await as(A, "insert into measurements (recording_id, session_id, study_id, modality, name, value, unit) values ($1,$2,$3,'eye','saccade_latency_median',$4,'ms')", [r, s, studyA, v]);
    }
    const z = (await as<any>(A, "select cohort_zscores($1) z", [sessA]))[0].z;
    expect(z.saccade_latency_median.n_controls).toBe(3);
    expect(z.saccade_latency_median.control_mean).toBeCloseTo(200);
    expect(typeof z.saccade_latency_median.z).toBe("number");
    expect((await as<any>(B, "select cohort_zscores($1) z", [sessA]))[0].z).toEqual({});
  });
});
