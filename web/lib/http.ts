import { NextResponse } from "next/server";
import type { ZodError } from "zod";

/** Postgres SQLSTATE -> HTTP status, for errors raised by our SQL functions. */
const PG_STATUS: Record<string, number> = {
  "28000": 401, // invalid device key
  "42501": 403, // not allowed / RLS
  P0002: 404,   // not found
  "22023": 400, // invalid parameter
  "22P02": 400, // invalid text representation (bad uuid etc.)
  "23514": 400, // check constraint
  "23502": 400, // not null
  "23503": 400, // foreign key
  "54000": 413, // batch too large
};

export function pgError(err: { code?: string; message: string }) {
  const status = (err.code && PG_STATUS[err.code]) || 500;
  return NextResponse.json({ error: status === 500 ? "internal error" : err.message, code: err.code }, { status });
}

export function zodError(err: ZodError) {
  return NextResponse.json(
    { error: "invalid request body", issues: err.issues.slice(0, 20).map((i) => ({ path: i.path.join("."), message: i.message })) },
    { status: 400 },
  );
}

export function bearer(req: Request): string | null {
  const h = req.headers.get("authorization") ?? "";
  const m = /^Bearer\s+(dk_[A-Za-z0-9_]+)$/.exec(h);
  return m ? m[1] : null;
}

export async function readJson(req: Request, maxBytes = 2_000_000): Promise<unknown> {
  const text = await req.text();
  if (text.length > maxBytes) throw Object.assign(new Error("payload too large"), { status: 413 });
  return JSON.parse(text);
}
