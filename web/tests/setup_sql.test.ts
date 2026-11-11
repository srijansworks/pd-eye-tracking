/** The hosted-setup SQL runs as the postgres admin (SQL editor) and must produce a working study + device key. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import { ROOT, as, makeDb } from "./helpers/db";

it("setup_hosted_study.sql creates study, members, participants and a usable device key", async () => {
  const db = await makeDb();
  const owner = "aaaaaaaa-0000-4000-8000-0000000000a1", mate = "aaaaaaaa-0000-4000-8000-0000000000a2";
  await db.query("insert into auth.users (id, email) values ($1, 'me@x.test'), ($2, 'mate@x.test')", [owner, mate]);
  const sql = readFileSync(join(ROOT, "supabase/admin/setup_hosted_study.sql"), "utf8")
    .replace("OWNER_EMAIL@example.com", "me@x.test").replace("TEAMMATE1@example.com", "mate@x.test");
  const results = await db.exec(sql);
  const keyRow = results.find((r) => r.fields.some((f) => f.name === "device_key"))!.rows[0] as any;
  expect(keyRow.device_key).toMatch(/^dk_[0-9a-f]{64}$/);

  const roles = (await db.query<any>("select user_id, role from study_members order by role")).rows;
  expect(roles).toEqual([{ user_id: mate, role: "researcher" }, { user_id: owner, role: "owner" }]);
  // The key works for a real device call, and the teammate sees the data through RLS.
  const sid = (await as<any>(db, null, "select device_create_session($1, 'SYN-101') s", [keyRow.device_key]))[0].s;
  expect(await as(db, mate, "select * from assessment_sessions where id = $1", [sid])).toHaveLength(1);
});
