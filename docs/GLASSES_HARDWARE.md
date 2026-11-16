# Glasses hardware plan (v1): camera, power, compute, heat

*Written 2026-11-16 from vendor listings and published specs, not from parts in hand. Every number marked
**(assumed)** or **(estimate)** must be checked on the real part before it is trusted. Research prototype, not a
medical device. Eye-safety review by a mentor or qualified adult is required before anyone wears the LEDs.*

CAD: [`hardware/glasses.scad`](../hardware/glasses.scad) (frame, camera mount, heat parts, eye models, camera view cone) and
[`hardware/compute_pack.scad`](../hardware/compute_pack.scad) (optional v2 pack). Both compile in OpenSCAD 2021.01;
`frame` and `mount` export to STL as single valid solids (`hardware/renders/*.stl`, previews `*.png`). **Nothing has
been test-printed**, and the pack file was only rendered once. Part sizes marked *assumed* in the CAD are guesses.
Render views: `-D 'view="assembly"'`, `"frame"`, `"mount"`, `"plate"`, `"section"`.

## Decision in one paragraph
Build v1 **tethered**: the glasses carry only a camera and two IR LEDs, and one thin USB-C cable goes to the laptop.
No battery and no compute on the head. The camera is a UVC device, so it needs a data cable anyway and the same
cable supplies its power. A wireless version would add a lithium cell and a radio next to the face, and the
wireless jitter would damage the saccade-latency measurement. The laptop runs the tracker at about 2.3 ms per frame.
If untethered use is wanted later, put a Raspberry Pi 5 and a power bank in a lanyard pack (v2) and keep the cable.

## Camera

| Option | Sensor / speed | Size | Price | Notes |
|---|---|---|---|---|
| **Waveshare OV9281 1MP Mono USB Camera (A), SKU 31671** (recommended v1) | OV9281 mono global shutter, MJPG 120 fps at 1280×720, 800×600, 640×480 | 25 × 25 mm, listed 27 g | about $27 | UVC, USB-C + 1.0 mm 4-pin, 5 V, **no IR filter** (so it sees 850 nm; add a visible-blocking filter), fixed M7 lens, 1.65 mm, listed FOV 120° |
| Arducam B0332 OV9281 USB, M12 lens | same sensor, 100–120 fps (listings disagree) | 38 × 38 mm | $46–60 | swappable M12 lens (can fit a narrower FOV), but too bulky for a frame |
| OV9281 / OV7251 MIPI modules | global shutter, 100–120 fps | 24 × 25 mm | $25–50 | need a Pi or Jetson and a CSI cable; no use for a laptop-first v1 |
| Pupil Labs 200 Hz eye camera | 192 × 192, 200 fps, global shutter | n/a | €650 | known good, but 20× the budget |
| USB endoscope / webcam boards | 30 fps, rolling shutter | small | $10–20 | too slow for saccade latency |

Why the Waveshare board: global shutter (no skew during saccades), mono (full IR sensitivity), 120 fps, UVC so
`eyetrack record --camera-type ir` works with no driver code, and the smallest board with all of that.
Its 800 × 600 mode is 4:3, the shape the pupil network was trained on, so `open_camera()` in
`eye-tracking/eyetrack/live.py` requests 800 × 600 at 120 fps MJPG.

Optics (estimate): at 32 mm from the pupil with a 110° horizontal FOV **(assumed)** the view is about 91 mm wide, so
800 px give about 8.8 px/mm and a 4 mm pupil is about 35 px wide. The requirement in `GLASSES_CAMERA_SPEC.md` is
at least 20 px. The synthetic camera used for all the software tests is about 9 px/mm.

Camera pose: it looks **up** at the eye from below. The software spec said 20°; I tested the tracker on synthetic
frames at 20°, 35° and 45° and the centre error stays about 0.05 px, so the CAD defaults to 35°, which puts the board
lower and clear of the straight-ahead view. The 25 mm board will still block the lowest part of the wearer's view.
If that is a problem, set `cam_az = 25` in the CAD to mount it from the temple side.

Known limits to check on arrival:
- MJPG at 120 fps costs CPU for decoding on the laptop (about 2–4 ms per 800 × 600 frame, estimate).
- macOS AVFoundation ignores the manual-exposure request in `Camera`; fixed exposure may need the vendor's UVC
  tool or a Linux box. Auto-exposure shifting brightness mid-recording is the main thing to watch.
- Frame timestamps are stamped on arrival in Python, so absolute latency has a constant offset (see `camera.py`).

## Illumination (eye safety first)
Two 850 nm wide-angle SMD LEDs, each on a small PCB beside the lens (the CAD shows 5 × 5 mm blocks), each with its own
resistor from the 5 V rail: R = (5 V − 1.5 V) / 15 mA ≈ 230 Ω, so use 220 Ω (about 16 mA, about 80 mW each).
Add a diffuser, keep the current low, and never look into a bare LED. A mentor must review the circuit against IEC
62471 limits before the first wear. Before wearing, check the brightness with a phone camera (most see IR) and by feel
(there should be no warmth on the skin).

Filter: the board has no IR filter, so add an 850 nm band-pass or a long-pass (about 800 nm or longer) disc in front
of the lens (about $10–25, check the lens thread/holder size). Without it the image changes with room light and
iris colour.

## Power: tether or battery?

| | Tethered USB-C (v1) | Lithium cell on the glasses | Lanyard pack (v2) |
|---|---|---|---|
| Added weight on the head | 0 g beyond the cable | 20–40 g cell + charger board | 0 g (cable only) |
| Safety near the face | no stored energy | cell 1–3 cm from the eye and skin | cell on the chest |
| Timing quality | wired, steady | needs a radio, jitter 5–30 ms (estimate) | wired to the pack, steady |
| Can it run 120 fps wirelessly? | n/a | 800 × 600 MJPG is about 20–40 Mbit/s: marginal on 2.4 GHz Wi-Fi | recorded on the pack, uploaded later |
| Verdict | **build this first** | reject | build second if portability is needed |

Camera draw is unmeasured. Budget (estimate): the board up to 250 mA at 5 V (1.25 W worst case) plus the LEDs about
32 mA, so the cable should carry well under the 500 mA USB 2.0 limit. **First bench step: a USB power meter on the
camera while it streams 800 × 600 at 120 fps.** If it ever exceeds 500 mA, power it from a powered hub.

## Heat
The camera dissipates most of its power in the USB/MJPEG bridge chip, and a 25 mm board with no airflow cannot shed
0.5–1 W without getting hot: about 40–80 K over ambient from natural convection alone (estimate). It must never
rest on the skin. Three measures, in order of effect:

1. **Orientation:** the lens and LEDs face the eye; the back of the board (and the hot chip) faces away from the face,
   with a printed shell that leaves at least 3 mm of air between board and skin. The frame is PETG, a poor conductor,
   which isolates the face. PLA softens near 60 °C and should not be used for the mount.
2. **Thermal mass, not fins:** the protocol runs about 111 s. A 25 × 25 × 6 mm aluminium block behind the board
   (about 10 g, about 9 J/K) absorbs 1 W for 2 minutes with a rise of about 13 K, ignoring losses. That makes a fanless
   heatsink the right choice for a short test. The CAD includes it (`sink_t`).
3. **Spreader:** a 55 mm aluminium strip on the outside of the right temple (not touching the skin) carries heat
   into more air. Aim for under 41 °C anywhere that touches skin; confirm with a thermocouple or IR thermometer
   after a 5 minute streaming test with the whole assembly on a mannequin or a mug-and-tape rig.

If the bridge chip still runs too hot: stream at 640 × 480 (less MJPEG work), lower the frame rate to 100, or
record only during the 2 minute protocol.

## Compute

| Where | Detector | Cost per frame | 120 fps? |
|---|---|---|---|
| Laptop (Apple A18 Pro class, measured) | `--ir-method fast` | median 2.3 ms, p95 9.1 ms on the synthetic glasses camera | yes (5.5% of frames, the network frames, exceed 8.3 ms) |
| Raspberry Pi 5 in a pack (estimate, not run) | `fast`, network every 30 frames or in a thread | tracking frames about 6–10 ms, network frames about 25–40 ms | marginal: needs the network in a background thread, or an ONNX/quantised model |
| On the glasses | none | n/a | rejected: heat and weight next to the face |

A Pi Zero 2 W is too slow for the network and the 120 fps camera path; do not use it for v1 or v2.

## Mass (target ≤ 60 g on the head; typical glasses 20–40 g)
Frame and temples PETG about 25 g, camera board about 10 g (the 27 g listing weight probably includes the cable),
aluminium block 10 g, strip 2 g, LED boards 2 g, cable pull on the right temple. Total about 50–55 g
(estimate). Strain-relieve the cable along the temple groove and behind the ear.

## Bill of materials, v1 (about $80–130, prices are estimates)
| Part | Qty | About |
|---|---|---|
| Waveshare OV9281 1MP Mono USB Camera (A) | 1 (buy 2) | $27 each |
| 850 nm SMD IR LED, wide angle, plus small PCBs | 2 (buy 6) | $5 |
| 220 Ω resistors | 2 (buy 10) | $1 |
| 850 nm band-pass or long-pass filter disc | 1 | $10–25 |
| Aluminium block 25 × 25 × 6 mm and strip 55 × 10 × 1.2 mm | 1 each | $5 |
| Thin flexible USB-C cable, 1.5–2 m | 1 | $8 |
| PETG filament, M2/M3 screws, thermal tape, double-sided tape | — | $15 |
| USB power meter (for the current check) | 1 | $10 |
| IR thermometer or thermocouple | 1 | $15 |
| Optional: prescription-less lenses/frame shell for looks | — | $0–20 |

## Build order
1. Open `hardware/glasses.scad` (`view="assembly"`) and confirm the pupil sits in the middle third of the camera view cone;
   adjust `cam_dist`, `cam_elev`, `cam_az` to taste.
2. When the camera arrives: power meter, `eyetrack check-camera --camera 1 --camera-type ir`, and a 10 s eye video with
   `eyetrack video eye.mp4 --out recordings/v1 --camera-type ir`. Target `pupil_found_fraction` > 0.9.
3. Print `view="mount"` in PETG, 0.2 mm layers, 4 walls; test-fit the board and the aluminium block before the frame.
4. Print `view="frame"` at 100% on a size M (ipd 63); adjust `ipd`, `head_w`, `vertex` to the wearer.
5. Add the filter and LEDs with a mentor present; test brightness with a phone camera; check temperature after 5 minutes.
6. Record `eye_v3` on a real face (also still open for the webcam path).

## What is not verified
- The CAD is untested as a print; board thickness, lens height, USB-C height and FOV are assumed.
- Camera current, board temperature, the FOV of the 800 × 600 mode and whether the filter fits the lens holder.
- Pi 5 timings, power-bank runtime and the pack's weight.
- Fit on a real face: the 25 mm board partly blocks the lower view in the default pose.
