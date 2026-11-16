# Glasses hardware plan (v1): camera, power, compute, heat

*Written 2026-11-16 from vendor listings and published specs, not from parts in hand. Every number marked
**(assumed)** or **(estimate)** must be checked on the real part before it is trusted. Research prototype, not a
medical device. Eye-safety review by a mentor or qualified adult is required before anyone wears the LEDs.*

CAD: [`hardware/glasses.scad`](../hardware/glasses.scad) is **v2: a bare camera head at the lower rim on a flex
cable, with the USB bridge board in a pod on the right temple**, so only the sensor and lens sit at the eye (the way
Meta's glasses hide theirs). v1, a 25 mm USB dev board hanging off the rim, is in git history (`268a7e9`).
[`hardware/compute_pack.scad`](../hardware/compute_pack.scad) is the optional lanyard pack. Everything compiles in
OpenSCAD 2021.01; `frame`, `mount` and `pod` export to STL as valid solids (`hardware/renders/`). **Nothing has
been test-printed.** Sizes marked *assumed* are guesses: the vendor listings for these modules contradict each other.
Views: `-D 'view="assembly"'`, `"frame"`, `"mount"`, `"pod"`, `"plate"`, `"section"`.

## Decision in one paragraph
Build v1 **tethered**: the glasses carry only a camera head and two IR LEDs, and one thin USB-C cable goes to the laptop.
No battery and no compute on the head. The camera is a UVC device, so it needs a data cable anyway and the same
cable supplies its power. A wireless version would add a lithium cell and a radio next to the face, and the
wireless jitter would damage the saccade-latency measurement. The laptop runs the tracker at about 2.3 ms per frame.
If untethered use is wanted later, put a Raspberry Pi 5 and a power bank in a lanyard pack (v2) and keep the cable.

## Camera
**v2 choice: an OV9281 module whose sensor head is separate from its USB board** (flex cable between them), instead of the
25 mm Waveshare board. Only the head (sensor, lens, two LEDs) sits at the eye; the USB/MJPEG bridge chip, which makes
most of the heat, sits in a pod on the temple.

| Option | Sensor / speed | At the eye | Notes |
|---|---|---|---|
| **OV9281 head + 100 mm flex + USB board** (v2 plan; e.g. Thanksbuyer SKU 103799, Innomaker, Sinoseen XLS11558) | OV9281 mono, 1280×800 at 120 fps, 1280×720 at 120, 640×360 at 240 (listing) | head about 10 mm **(assumed)** | $28–49. Listing conflicts: says "global shutter" and also "rolling shutter"; M12 lens (EFL 2.6 mm, 81°) which needs a holder of at least 14 mm; UVC not stated. **Ask the seller or buy one and test before committing.** Draw 160–260 mA at 5 V |
| Waveshare OV9281 USB (A), SKU 31671 (v1) | OV9281, MJPG 120 fps at 800×600 | 25 × 25 mm board | $27, UVC, no IR filter, listed 120° FOV. Safe fallback if the flex-head listings fail |
| OmniVision OVM6211 | 400×400 at 120 fps, global shutter, about 50° FOV | **3.2 mm cube** | The Meta-class part. Bare chip on solder balls: needs a custom flex and a MIPI-to-USB bridge. A v3 goal, not for this build |
| Pupil Labs 200 Hz eye camera | 192×192, 200 fps | n/a | €650 |
| USB endoscope boards | 30 fps, rolling shutter | small | too slow |

Why OV9281: global shutter (no skew in saccades), mono, 120 fps, and high near-IR sensitivity. Meta's Aria glasses use
400×400 to 640×480 eye cameras, so 800×600 is more than enough; the software already asks for it
(`open_camera()` in `eye-tracking/eyetrack/live.py`).

Optics (estimate): the 81° listing FOV (axis unknown, treated as horizontal) at 24 mm gives a 41 mm wide view, so
a 4 mm pupil is about 78 px at 800 px wide, over the 20 px minimum. Pose: the head sits 24 mm from the pupil, looking up
50°, which tucks it into the lower rim: the cradle is about 23 × 13 mm, 2 mm below the rim and 4 mm in front of it, a
bump rather than a box. The software tracker on synthetic frames: sub-pixel to 50° (worst error 2.4 px), marginal at
55° (4.3 px), fails at 60°. Real eyelids and lashes will be harder than synthetic ones, so a steep angle is a risk until
tested; lower `cam_elev` (and raise `cam_dist`) if lashes cover the pupil. Set `cam_az = 25` to view from the temple side.

Known limits to check on arrival:
- Which lens holder the head has (the CAD cradle assumes a 10 × 10 × 8 mm head; an M12 holder needs `head_x/head_y = 14`).
- Whether the flex is long enough: the CAD route is about 63 mm against the 100 mm listed (`flex_run_mm` echo).
- MJPG at 120 fps costs the laptop about 2–4 ms of decode per frame (estimate).
- macOS ignores the manual-exposure request in `Camera`; auto-exposure drift is the main thing to watch.

## Illumination (eye safety first)
Two 850 nm wide-angle SMD LEDs, one each side of the camera head, inside the cradle (the CAD shows 3 × 3 mm blocks), each with its own
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
Most of the power goes into the USB/MJPEG bridge chip (listings give 160–260 mA at 5 V, so 0.8–1.3 W, or 180 mW on
another listing). In v2 that chip is on the pod, on the **outside** of the right temple, away from the face. The head
at the eye is just a sensor plus two LEDs (about 0.2 W, estimate).

1. **Orientation:** the pod's hot board faces outward, under a 2.5 mm aluminium cover plate (about 4.7 g, about 4 J/K).
   The temple and cradle are PETG, a poor conductor, so the skin sees little. PLA softens near 60 °C and should not be used.
2. **Thermal mass:** the protocol runs about 111 s. The cover plus the board and case absorb 1 W for 2 minutes with a rise
   of a few tens of kelvin at worst (estimate), so the pod will be warm but short tests are fine. If a thermocouple
   says otherwise, thicken the cover (steel or copper) or add fins.
3. **Check on a mannequin or mug-and-tape rig:** after 5 minutes of streaming, anything touching skin should stay under
   about 41 °C. Measure; these are estimates.

If it runs hot: stream at 640 × 480, lower the frame rate, or record only during the 2-minute protocol.

## Compute

| Where | Detector | Cost per frame | 120 fps? |
|---|---|---|---|
| Laptop (Apple A18 Pro class, measured) | `--ir-method fast` | median 2.3 ms, p95 9.1 ms on the synthetic glasses camera | yes (5.5% of frames, the network frames, exceed 8.3 ms) |
| Raspberry Pi 5 in a pack (estimate, not run) | `fast`, network every 30 frames or in a thread | tracking frames about 6–10 ms, network frames about 25–40 ms | marginal: needs the network in a background thread, or an ONNX/quantised model |
| On the glasses | none | n/a | rejected: heat and weight next to the face |

A Pi Zero 2 W is too slow for the network and the 120 fps camera path; do not use it for v1 or v2.

## Mass (target ≤ 60 g on the head; typical glasses 20–40 g)
Frame and temples PETG about 25 g, head and cradle about 6 g, pod case and board about 11 g, aluminium cover 4.7 g, flex and
LEDs about 1 g, USB cable pull extra. About 48 g (estimate). Strain-relieve the USB-C cable along the temple groove.

## Bill of materials, v2 (about $90–150, prices are estimates)
| Part | Qty | About |
|---|---|---|
| OV9281 USB module with detachable sensor head on a flex (see Camera; confirm shutter, UVC, head size, flex length) | 1 (buy 2) | $28–49 each |
| Fallback: Waveshare OV9281 USB (A) | 1 | $27 |
| 850 nm SMD IR LED, wide angle, small PCBs | 2 (buy 6) | $5 |
| 220 Ω resistors, thin wire (30 AWG) for the LED pair along the flex | — | $3 |
| 850 nm band-pass or long-pass filter, cut to the lens size | 1 | $10–25 |
| Aluminium sheet 2.5 mm for the pod cover | — | $5 |
| Thin flexible USB-C cable, 1.5–2 m | 1 | $8 |
| PETG filament, M2 screws, tapes | — | $15 |
| USB power meter, IR thermometer or thermocouple | 1 each | $25 |

The LEDs take 5 V through their resistors from the USB board's pads or the USB-C break-out in the pod, with the two wires
riding along the flex route.

## Build order
1. Open `hardware/glasses.scad` (`view="assembly"`) and confirm the pupil sits in the middle third of the camera view cone;
   adjust `cam_dist`, `cam_elev`, `cam_az` to taste.
2. When the camera arrives: power meter, `eyetrack check-camera --camera 1 --camera-type ir`, and a 10 s eye video with
   `eyetrack video eye.mp4 --out recordings/v1 --camera-type ir`. Target `pupil_found_fraction` > 0.9.
3. Print `view="mount"` and `view="pod"` in PETG, 0.2 mm layers, 4 walls; test-fit the real head and USB board and edit the `head_*` and `pod_board` sizes before printing the frame.
4. Print `view="frame"` at 100% on a size M (ipd 63); adjust `ipd`, `head_w`, `vertex` to the wearer.
5. Add the filter and LEDs with a mentor present; test brightness with a phone camera; check temperature after 5 minutes.
6. Record `eye_v3` on a real face (also still open for the webcam path).

## What is not verified
- The CAD is untested as a print; head size, pod board size, flex length and FOV are assumed from conflicting listings.
- Whether the chosen flex-head module is really global shutter and UVC (one listing says both global and rolling shutter).
- Camera current, pod temperature, the FOV of the 800 × 600 mode and whether the filter fits the lens holder.
- Pi 5 timings, power-bank runtime and the pack's weight.
- Fit on a real face: the cradle is about 23 mm wide (head plus two LEDs) and 13 mm tall and tucks into the lower rim, so it blocks little (only the wearer's view below about 38° downward), but check it.
