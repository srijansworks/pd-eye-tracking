# Sensor data format: for the eye, wrist and gait teams

Every sensor uploads **one JSON "measurement batch" per recording** to the same endpoint.
Machine-readable definition: [`schema/measurement-batch.v1.schema.json`](schema/measurement-batch.v1.schema.json).
Real example from the eye pipeline: [`examples/eye-batch.example.json`](examples/eye-batch.example.json).

```jsonc
POST /api/v1/ingest
Authorization: Bearer dk_...            // your device key
{
  "schema_version": "1.0",
  "session_id": "6f0c…",                // from POST /api/v1/sessions
  "recording": {
    "modality": "wrist",                // eye | wrist | gait | other
    "started_at": "2026-11-04T18:00:01.250Z",   // UTC, ISO-8601, milliseconds
    "ended_at":   "2026-11-04T18:01:41.250Z",
    "sample_rate_hz": 100,
    "protocol": "rest_tremor_v1",
    "is_synthetic": false,
    "clock": { "source": "ble_host", "offset_ms": -42, "sync_event": "sync_tap" },
    "device_info": { "model": "MPU-6050 on ESP32", "firmware": "0.3.1", "placement": "left wrist" },
    "quality": { "flags": [], "dropped_samples": 3 }
  },
  "measurements": [
    { "name": "tremor_peak_frequency", "value": 5.1, "unit": "Hz",
      "task": "rest", "confidence": 0.8, "quality_flags": [], "metadata": { "axis": "x" } }
  ],
  "events": [
    { "t": "2026-11-04T18:00:02.000Z", "kind": "sync_tap", "task": null, "data": {} }
  ]
}
```

## Field rules
| Field | Rule |
|---|---|
| `name` | `snake_case`, 2–64 chars, starts with a letter. Put the statistic in the name: `stride_length_mean`, not `stride_length` + metadata. |
| `value` | A finite number. **Never** send NaN or Infinity; leave the measurement out and say why in `recording.quality`. |
| `unit` | Short and consistent: `ms`, `s`, `Hz`, `deg`, `deg/s`, `m`, `m/s`, `m/s^2`, `g`, `1/min`, `1/s`, `ratio`, `px`, `count`. Ratios are 0–1, not percent. |
| `t` | `null` = summary over the recording/task (the default). Set it only for individual time points. |
| `task` | Protocol segment (`fixation`, `prosaccade`, `rest`, `walk_10m`, `finger_tap`…) or `all`. |
| `confidence` | 0–1 data-quality score from *your* pipeline (document how you compute it). |
| `quality_flags` | Short strings, e.g. `low_fps`, `undersampled`, `sensor_saturated`, `low_battery`. |
| `events` | Things that happened at an instant: stimulus changes, `sync_tap`, `walk_start`, `turn`. |

Limits: ≤ 5000 measurements and ≤ 5000 events per batch, ≤ 2 MB body. **Raw
high-rate samples do not go here.** Keep them as files (CSV/Parquet) on the device for now.

## Time alignment across devices
1. All timestamps are **UTC with milliseconds**. Make sure each device's clock is synced (NTP or phone/laptop time).
2. Each recording states `clock.offset_ms`: the correction to add to device time to get the
   session's reference time (the eye laptop is the reference, so its offset is 0).
3. For sub-second alignment, perform a **sync event** that every sensor can see. Recommended:
   the participant taps the wrist sensor on the table while looking at the camera. Each device
   logs a `sync_tap` event. The difference between the timestamps gives `offset_ms`.
4. All recordings of one visit share one `session_id`, so the eye, wrist and gait data are
   associated without any extra matching.

## Measurement name registry
Eye (implemented): `blink_rate`, `blink_duration_mean`, `fixation_bcea_68`, `fixation_sd_x`,
`fixation_sd_y`, `intrusive_saccade_rate`, `square_wave_jerk_rate`, `fixation_duration_mean`,
`saccade_latency_median`, `saccade_latency_sd`, `saccade_amplitude_median`,
`saccade_peak_velocity_median`, `saccade_gain_median`, `saccade_direction_error_rate`,
`pursuit_velocity_gain`, `pursuit_phase_lag`, `pursuit_catchup_saccade_rate`,
`valid_frame_fraction`, `effective_fps`, `iris_diameter_px`, `calibration_rmse`.

Wrist / gait: add your names here in a pull request **before** you start uploading, so the
dashboard and future models agree on meaning and units. Examples: `tremor_peak_frequency`,
`tremor_power_4_6hz`, `finger_tap_rate`, `stride_time_cv`, `gait_speed_mean`, `turn_duration`.

## Integration checklist for a new sensor
1. Ask a study researcher to create a device key:
   `select * from create_device('<study_id>', 'wrist hub 1', 'wrist');` (the key is shown once; store it in your `.env`).
2. Produce a batch that validates against the JSON Schema (Python: `jsonschema`; JS: the zod schema in `web/lib/schema.ts`).
3. Create a session (`POST /api/v1/sessions` with `participant_code`), or upload into an
   existing `session_id` that the eye laptop created for the same visit.
4. `POST /api/v1/ingest`. Retrying the same batch is safe: it returns `duplicate: true`.
