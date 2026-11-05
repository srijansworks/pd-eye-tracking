/**
 * POST /api/v1/ingest — upload one measurement batch from a device.
 * Auth: `Authorization: Bearer dk_...` (device key). Body: docs/DATA_FORMAT.md
 *
 * Validation happens twice on purpose: zod here gives friendly 400 errors,
 * and the SQL function re-checks everything that matters for security.
 */
import { NextResponse } from "next/server";
import { MeasurementBatch } from "@/lib/schema";
import { bearer, pgError, readJson, zodError } from "@/lib/http";
import { deviceClient } from "@/lib/supabase/server";

export async function POST(req: Request) {
  const key = bearer(req);
  if (!key) return NextResponse.json({ error: "missing device key" }, { status: 401 });

  let body: unknown;
  try {
    body = await readJson(req);
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? "invalid JSON" }, { status: e.status ?? 400 });
  }
  const parsed = MeasurementBatch.safeParse(body);
  if (!parsed.success) return zodError(parsed.error);

  const { data, error } = await deviceClient().rpc("ingest_batch", { p_device_key: key, p_batch: parsed.data });
  if (error) return pgError(error);
  return NextResponse.json(data, { status: data?.duplicate ? 200 : 201 });
}
