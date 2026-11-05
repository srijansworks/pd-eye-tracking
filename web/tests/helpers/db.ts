/** Shared PGlite setup: Supabase stubs + all migrations. */
import { PGlite } from "@electric-sql/pglite";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

export const ROOT = join(__dirname, "..", "..", "..");
const MIG = join(ROOT, "supabase", "migrations");

const SUPABASE_STUBS = `
  create role anon nologin; create role authenticated nologin;
  create schema auth;
  create table auth.users (id uuid primary key, email text, raw_user_meta_data jsonb default '{}');
  create function auth.uid() returns uuid language sql stable as
    $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema auth to anon, authenticated;
  grant execute on function auth.uid() to anon, authenticated;
  grant usage on schema public to anon, authenticated;
  create schema storage;
  create table storage.buckets (id text primary key, name text, public boolean);
  create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text);
  alter table storage.objects enable row level security;
  create function storage.foldername(name text) returns text[] language sql immutable as
    $$ select (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'), 1) - 1] $$;
  grant usage on schema storage to authenticated;
  grant execute on function storage.foldername(text) to authenticated;
  grant select, insert, delete on storage.objects to authenticated;
`;

export async function makeDb() {
  const db = new PGlite();
  await db.exec(SUPABASE_STUBS);
  for (const f of readdirSync(MIG).sort()) await db.exec(readFileSync(join(MIG, f), "utf8"));
  return db;
}

/** Run SQL as a signed-in user (uuid) or as anon (null), the way PostgREST does. */
export async function as<T = any>(db: PGlite, who: string | null, sql: string, params: any[] = []) {
  await db.exec("reset role");
  await db.query("select set_config('request.jwt.claim.sub', $1, false)", [who ?? ""]);
  await db.exec(who ? "set role authenticated" : "set role anon");
  try {
    return (await db.query<T>(sql, params)).rows;
  } finally {
    await db.exec("reset role");
  }
}
