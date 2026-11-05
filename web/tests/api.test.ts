/**
 * API integration tests: the REAL Next.js route handlers, the REAL zod
 * schema and the REAL SQL functions (in PGlite). Only the HTTP hop to
 * Supabase/PostgREST is replaced: `deviceClient().rpc(fn, args)` runs
 * `select public.fn(args)` as the anon role, which is what PostgREST does.
 */
import type { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ROOT, as, makeDb } from "./helpers/db";

let db: PGlite;

vi.mock("@/lib/supabase/server", () => ({
  deviceClient: () => ({
    rpc: async (fn: string, args: Record<string, unknown>) => {
      const names = Object.keys(args);
      const sql = `select public.${fn}(${names.map((n, i) => `${n} => $${i + 1}`).join(", ")}) as r`;
      const vals = names.map((n) => (typeof args[n] === "object" && args[n] !== null ? JSON.stringify(args[n]) : args[n]));
      try {
        return { data: (await as<any>(db, null, sql, vals))[0].r, error: null };
      } catch (e: any) {
        return { data: null, error: { code: e.code, message: e.message } };
      }
    },
  }),
  userClient: async () => { throw new Error("not used in these tests"); },
}));

const { POST: ingest } = await import("@/app/api/v1/ingest/route");
const { POST: createSession } = await import("@/app/api/v1/sessions/route");
const { MeasurementBatch } = await import("@/lib/schema");

const EXAMPLE = JSON.parse(readFileSync(join(ROOT, "docs/examples/eye-batch.example.json"), "utf8"));
const A = "aaaaaaaa-0000-4000-8000-000000000001";
let key = "";

const post = (handler: (r: Request) => Promise<Response>, body: unknown, k: string | null = key) =>
  handler(new Request("http://test/api", {
    method: "POST", body: typeof body === "string" ? body : JSON.stringify(body),
    headers: { "content-type": "application/json", ...(k ? { authorization: `Bearer ${k}` } : {}) },
  }));

beforeAll(async () => {
  db = await makeDb();
  await db.query("insert into auth.users (id, email) values ($1, 'a@x.test')", [A]);
  const study = (await as<any>(db, A, "insert into studies (name) values ('API test study') returning id"))[0].id;
  await as(db, A, "insert into participants (study_id, code, cohort, is_synthetic) values ($1, 'SYN-001', 'synthetic', true)", [study]);
  key = (await as<any>(db, A, "select * from create_device($1, 'cam', 'eye')", [study]))[0].device_key;
});

describe("shared schema contract", () => {
  it("zod accepts the batch produced by the Python pipeline", () => {
    const r = MeasurementBatch.safeParse(EXAMPLE);
    expect(r.success, JSON.stringify(!r.success && r.error.issues.slice(0, 3))).toBe(true);
  });
  it("zod rejects NaN-like values, bad names, unknown fields", () => {
    const bad = structuredClone(EXAMPLE);
    bad.measurements[0].name = "Saccade Latency";
    expect(MeasurementBatch.safeParse(bad).success).toBe(false);
    expect(MeasurementBatch.safeParse({ ...EXAMPLE, extra: 1 }).success).toBe(false);
  });
});

describe("POST /api/v1/sessions + /api/v1/ingest (device flow)", () => {
  it("full flow: create session -> upload Python batch -> stored", async () => {
    const r1 = await post(createSession, { participant_code: "SYN-001", protocol: "eye_v1" });
    expect(r1.status).toBe(201);
    const { session_id } = await r1.json();

    const r2 = await post(ingest, { ...EXAMPLE, session_id });
    expect(r2.status).toBe(201);
    const body = await r2.json();
    expect(body.n_measurements).toBe(EXAMPLE.measurements.length);

    const r3 = await post(ingest, { ...EXAMPLE, session_id });   // retry = idempotent
    expect(r3.status).toBe(200);
    expect((await r3.json()).duplicate).toBe(true);

    const rows = (await db.query<any>("select name, value, unit, confidence from measurements where session_id = $1 order by name", [session_id])).rows;
    const lat = rows.find((r: any) => r.name === "saccade_latency_median");
    expect(lat.unit).toBe("ms");
    expect(lat.value).toBeGreaterThan(100);
  });

  it("maps errors to sensible HTTP codes", async () => {
    expect((await post(ingest, EXAMPLE, null)).status).toBe(401);                    // no key
    expect((await post(ingest, { ...EXAMPLE, session_id: crypto.randomUUID() }, "dk_bad")).status).toBe(401);
    expect((await post(ingest, { ...EXAMPLE, session_id: crypto.randomUUID() })).status).toBe(404); // unknown session
    expect((await post(ingest, "{not json")).status).toBe(400);
    const r = await post(ingest, { ...EXAMPLE, schema_version: "2.0" });
    expect(r.status).toBe(400);
    expect((await r.json()).issues.length).toBeGreaterThan(0);
    expect((await post(createSession, { participant_code: "NOPE" })).status).toBe(404);
  });
});
