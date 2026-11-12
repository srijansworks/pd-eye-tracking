# Eye-tracking glasses: what the software needs from the hardware

*From the software team to the hardware team. Based on the near-eye IR pipeline in
`eye-tracking/eyetrack/nearir/` and its synthetic benchmark. Verify every part number and
datasheet yourselves before buying; these are requirements, not a shopping list.*

## Why glasses at all
Three real webcam recordings showed that the main error source is the head moving relative to the
camera: saccade gain drifted 0.84 → 0.72 as posture changed. A camera fixed to the head removes that.
In simulation, the glasses pipeline at 120 fps measures saccade gain, pursuit gain and pupil size
almost exactly (gain 0.949 vs 0.95 true, pupil 4.02 vs 4.01 mm). The webcam can't measure pupil size at all.

## Camera requirements (one eye is enough to start)
| Requirement | Minimum | Better | Why |
|---|---|---|---|
| Frame rate | **120 fps** | 200–250 fps | 120: latency to 8 ms, square-wave jerks visible. ≥ 250 for true saccade peak velocity |
| Shutter | Global shutter preferred | Global | Rolling shutter skews the pupil during fast saccades |
| Sensitivity | Works at **850 nm** (monochrome sensors are best) | — | Dark-pupil IR imaging |
| Filter | **IR-pass filter** (blocks visible light) | — | Makes the image independent of room light and iris colour |
| Pixels across the eye | Pupil ≥ 20 px wide (eye region ~200 px) | 300+ px | The detector reaches sub-pixel accuracy at this size |
| Interface | USB UVC (shows up as a normal webcam) | — | Works with `eyetrack --camera-type ir` with no driver code |
| Exposure | Manual / fixed exposure | — | Auto-exposure changes brightness and frame rate mid-recording |

Candidate types to evaluate (check the datasheets): small monochrome global-shutter USB camera boards
(e.g. OV9281-sensor modules advertise 120+ fps), or an existing open eye-camera design from the Pupil Labs
DIY community. Endoscope-style mini cameras are usually 30 fps rolling shutter, which is too slow.

## Illumination
- 1–2 **850 nm IR LEDs** beside the camera, aimed at the eye. They also create the glints the detector already handles.
- **Eye safety first:** use low-power LEDs with a current-limiting resistor and a diffuser, keep exposure within IEC 62471 limits,
  and have a mentor or qualified adult review the circuit **before** anyone wears it. Never look into a bare high-power IR LED.

## Mounting
- Camera **below** the eye, looking up at about 20° (what the software models), 3–5 cm from the eye.
- The camera must not move relative to the head: a rigid frame, not a flexible arm.
- Keep the eyelashes out of the line of sight to the pupil as much as possible.

## Timing and sync with the wrist sensor
- Each frame gets a timestamp on the computer. The wrist sensor timestamps its own samples.
- Do the **sync tap** at the start of every session: tap the wrist sensor on the table once while looking at
  the screen. Both devices log a `sync_tap` event, and the difference gives the clock offset (see `docs/DATA_FORMAT.md`).

## How to test the first prototype (no extra code needed)
```bash
cd eye-tracking
.venv/bin/eyetrack check-camera --camera 1 --camera-type ir      # camera index of the glasses camera
.venv/bin/eyetrack record --out recordings/glasses01 --camera 1 --camera-type ir --screen-width-cm 28 --distance-cm 50
```
Also record a 10-second video of the eye with any camera app and run
`eyetrack video eye.mp4 --out recordings/v1 --camera-type ir` to see whether the pupil is found
(`pupil_found_fraction` should be > 0.9).

## Optional later
- A ruler or printed dot of known size in front of the camera once, to set `--mm-per-px` (pupil size in mm).
- A visible LED pointed at the eye for a **pupillary light reflex** test (a constriction measurement relevant to PD research).
