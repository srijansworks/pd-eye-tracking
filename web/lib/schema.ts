/**
 * Measurement batch v1 — the shared upload format for ALL sensors.
 * Mirrors docs/schema/measurement-batch.v1.schema.json (tests check both
 * accept the same example). Change both together and bump schema_version.
 */
import { z } from "zod";

const isoDateTime = z.string().datetime({ offset: true });

export const Modality = z.enum(["eye", "wrist", "gait", "other"]);

export const Measurement = z
  .object({
    name: z.string().regex(/^[a-z][a-z0-9_]{1,63}$/, "snake_case, 2-64 chars"),
    value: z.number().finite(),
    unit: z.string().min(1).max(32),
    t: isoDateTime.nullable().optional(),
    task: z.string().max(64).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    quality_flags: z.array(z.string()).optional(),
    metadata: z.record(z.unknown()).optional(),
  })
  .strict();

export const SessionEvent = z
  .object({
    t: isoDateTime,
    kind: z.string().min(1).max(64),
    task: z.string().max(64).nullable().optional(),
    data: z.record(z.unknown()).optional(),
  })
  .strict();

export const MeasurementBatch = z
  .object({
    schema_version: z.literal("1.0"),
    session_id: z.string().uuid(),
    recording: z
      .object({
        modality: Modality,
        started_at: isoDateTime,
        ended_at: isoDateTime.nullable().optional(),
        sample_rate_hz: z.number().nonnegative().nullable().optional(),
        protocol: z.string().max(64).nullable().optional(),
        is_synthetic: z.boolean().optional(),
        clock: z
          .object({ source: z.string().optional(), offset_ms: z.number().optional(), sync_event: z.string().nullable().optional() })
          .passthrough()
          .optional(),
        device_info: z.record(z.unknown()).optional(),
        quality: z.record(z.unknown()).optional(),
        raw_media_stored: z.boolean().optional(),
      })
      .strict(),
    measurements: z.array(Measurement).max(5000),
    events: z.array(SessionEvent).max(5000).optional(),
  })
  .strict();

export type MeasurementBatch = z.infer<typeof MeasurementBatch>;

export const CreateSession = z.object({
  participant_code: z.string().regex(/^[A-Za-z0-9_-]{2,32}$/),
  protocol: z.string().max(64).optional(),
});
