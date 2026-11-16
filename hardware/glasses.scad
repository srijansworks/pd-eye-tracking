// Eye-tracking glasses, v1 concept (tethered USB-C, one eye camera). Units: mm.
//
// Rendered and STL-exported with OpenSCAD 2021.01 (2026-11-16): frame and mount export as single valid
// solids. NOT test-printed. Every number marked ASSUMED must be checked against the real part before printing.
//
// Coordinates: x = wearer's RIGHT, y = up, z = forward (away from the face). Origin = corneal apex of
// the wearer's right eye is at (+ipd/2, 0, 0); the left eye is at (-ipd/2, 0, 0).
//
//   view = "assembly"  everything, with eye models + camera view cone (default)
//   view = "frame"     printable frame front + temples only
//   view = "mount"     printable camera mount only
//   view = "plate"     frame + mount laid flat for printing
//   view = "section"   assembly cut at the right pupil plane
// Command line:  openscad -o glasses.png --camera=0,0,10,70,0,25,420 -D 'view="assembly"' glasses.scad

view = "assembly";

// ---------- face / frame ----------
ipd          = 63;     // pupil distance, adult average; make a size S/M/L by changing this
vertex       = 13;     // cornea apex to back face of the frame front
front_t      = 5;      // frame front thickness (z)
lens_w       = 50;     // lens opening
lens_h       = 38;
rim          = 5;      // frame material around each opening
bridge_w     = 18;
temple_len   = 135;
temple_w     = 5;      // temple thickness (x)
temple_h     = 8;      // temple height (y)
head_w       = 140;    // distance between the temple inner faces

// ---------- camera: Waveshare OV9281 1MP Mono USB Camera (A), SKU 31671 ----------
// Listed 25 x 25 mm, 27 g, M7 fixed-focus lens, USB-C + 1.0 mm 4-pin, 5 V. Thickness/lens height ASSUMED.
cam_pcb      = 25;
cam_pcb_t    = 1.6;    // ASSUMED
cam_lens_d   = 9;      // ASSUMED M7 barrel + holder
cam_lens_h   = 9;      // ASSUMED: board face to front of lens
cam_conn_h   = 4;      // ASSUMED USB-C receptacle height on the back
cam_hfov     = 110;    // ASSUMED horizontal FOV (listing says 120 deg, probably diagonal)

// where the camera sits relative to the right eye
cam_dist     = 32;     // lens to pupil
cam_elev     = 35;     // looks UP at the eye by this angle (software default is 20, tested to 45)
cam_az       = 0;      // 0 = straight below the eye; +20..30 = from the temple side (clears the view)
cam_x_shift  = 0;

// ---------- heat ----------
sink_t       = 6;      // aluminium thermal-mass block behind the board (25x25x6 ~ 10 g ~ 9 J/K)
spreader_len = 55;     // aluminium strip along the temple that carries the heat away from the face

// ---------- IR LEDs: 2 x 850 nm, wide-angle, on small PCBs either side of the lens ----------
led_offset   = 17;     // from camera axis, along the board
led_size     = 5;      // 5 x 5 x 2 block stands for a 3535 package (ASSUMED)

// ---------- helpers ----------
$fn = 48;
module rrect(w, h, r, t) {
    linear_extrude(height = t)
        offset(r = r) square([w - 2 * r, h - 2 * r], center = true);
}

// the right eye: ball + cornea + pupil, apex at z = 0
module eye(pupil_d = 4) {
    color("white") translate([0, 0, -12]) sphere(d = 24);
    color("lightblue") translate([0, 0, -2.5]) sphere(d = 12);   // iris disc stand-in (ASSUMED)
    color("black") translate([0, 0, -0.2]) cylinder(d = pupil_d, h = 0.4, center = true);
}

// unit vector from camera to pupil, and the camera position
function cam_pos() = [ipd / 2 + cam_x_shift + cam_dist * cos(cam_elev) * sin(cam_az),
                      -cam_dist * sin(cam_elev),
                      cam_dist * cos(cam_elev) * cos(cam_az)];

// rotate children so +z points from the camera toward the right pupil:
// pitch about x first (up toward the eye), then yaw about y
module aim_at_pupil() {
    p = cam_pos();
    v = [ipd / 2 - p[0], 0 - p[1], 0 - p[2]];
    L = norm(v);
    translate(p)
        rotate([0, atan2(v[0], v[2]), 0])
        rotate([-asin(v[1] / L), 0, 0])
        children();
}

// ---------- frame ----------
module frame_front() {
    difference() {
        union() {
            for (s = [-1, 1]) translate([s * ipd / 2, 0, vertex])
                rrect(lens_w + 2 * rim, lens_h + 2 * rim, 14, front_t);
            translate([-bridge_w / 2 - 1, -4, vertex]) cube([bridge_w + 2, 10, front_t]);
            // end pieces carry the hinges
            for (s = [-1, 1]) translate([s * (head_w / 2 - 2), 0, vertex - 2]) cube([8, temple_h + 4, front_t + 2], center = true);
        }
        for (s = [-1, 1]) translate([s * ipd / 2, 0, vertex - 1])
            rrect(lens_w, lens_h, 11, front_t + 2);
        // nose cut-out
        translate([0, -lens_h / 2 + 2, vertex - 1]) cylinder(d = 14, h = front_t + 2);
    }
}

module temple(s) {   // s = +1 right, -1 left; straight bar with a groove for the USB cable on the right
    // +z is forward, so the temples run BACKWARD (-z) from the frame toward the ears
    translate([s * head_w / 2 - (s > 0 ? 0 : temple_w), -temple_h / 2, vertex + 1 - temple_len])
    difference() {
        cube([temple_w, temple_h, temple_len], center = false);
        if (s > 0) translate([temple_w - 2.2, temple_h / 2 - 1.8, -1]) cube([2.4, 3.6, temple_len - 4]);  // cable groove, 3.6 mm
    }
}

// ---------- camera assembly ----------
module camera_board() {
    color("darkgreen") translate([0, 0, -cam_pcb_t]) cube([cam_pcb, cam_pcb, cam_pcb_t], center = true);
    color("dimgray") cylinder(d = cam_lens_d, h = cam_lens_h);                 // lens, +z = toward the eye
    color("silver") translate([0, -cam_pcb / 2 + 5, -cam_pcb_t - cam_conn_h / 2]) cube([9, 7.5, cam_conn_h], center = true);
    for (s = [-1, 1]) color("firebrick") translate([s * led_offset, 0, 1]) cube([led_size, led_size, 2], center = true);
}

module thermal_block() {   // sits behind the board, away from the face
    color("silver") translate([0, 0, -cam_pcb_t - cam_conn_h - sink_t / 2 - 0.5])
        cube([cam_pcb, cam_pcb, sink_t], center = true);
}

// printable bracket: a shell holding the board and the thermal block, joined to the lower rim by a wedge
module shell_outer() {   // camera coordinates (+z toward the eye)
    translate([0, 0, -cam_pcb_t - cam_conn_h - sink_t - 2.5])
        rrect(cam_pcb + 5, cam_pcb + 5, 3, cam_pcb_t + cam_conn_h + sink_t + 2.5 + 3);
}
module shell_cavities() {
    // pocket for board + block (open toward the eye)
    translate([0, 0, -cam_pcb_t - cam_conn_h - sink_t - 0.5]) rrect(cam_pcb + 0.4, cam_pcb + 0.4, 1, cam_pcb_t + cam_conn_h + sink_t + 3.5);
    // window for lens and LEDs
    translate([0, 0, -1]) rrect(cam_pcb - 3, cam_pcb - 3, 2, 8);
    // USB-C exit through the side wall
    translate([cam_pcb / 2, -cam_pcb / 2 + 5, -cam_pcb_t - cam_conn_h / 2]) cube([10, 10, 6], center = true);
}
module mount_wedge() {   // world coordinates: hull from the shell's front slab to the frame's lower rim
    hull() {
        aim_at_pupil() translate([0, 0, -4]) rrect(cam_pcb + 5, cam_pcb + 5, 3, 4);
        translate([ipd / 2 + cam_x_shift, -(lens_h / 2 + rim / 2), vertex + front_t / 2]) cube([cam_pcb + 5, rim, front_t], center = true);
    }
}

module spreader_strip() {   // aluminium strip glued to the outside of the right temple (not touching skin)
    color("silver") translate([head_w / 2 + temple_w, -5, vertex - 4 - spreader_len])
        cube([1.2, 10, spreader_len]);
}

module fov_cone() {   // camera view cone, transparent
    p = cam_pos();
    L = cam_dist + 18;
    color("yellow", 0.12) aim_at_pupil() rotate([0, 0, 0])
        hull() { cube([0.1, 0.1, 0.1], center = true);
                 translate([0, 0, L]) cube([2 * L * tan(cam_hfov / 2), 1.5 * L * tan(cam_hfov / 2), 0.1], center = true); }
}

module camera_assembly() {
    aim_at_pupil() { camera_board(); thermal_block(); }
}

module mount_printable() {
    difference() {
        union() { aim_at_pupil() shell_outer(); mount_wedge(); }
        aim_at_pupil() shell_cavities();
    }
}

// ---------- assembly ----------
module glasses() {
    color("slategray") frame_front();
    color("slategray") temple(1);
    color("slategray") temple(-1);
    color("steelblue") mount_printable();
    camera_assembly();
    spreader_strip();
}

module eyes() { for (s = [-1, 1]) translate([s * ipd / 2, 0, 0]) eye(); }

// ---------- views ----------
if (view == "assembly") { glasses(); eyes(); fov_cone(); }
else if (view == "frame") { frame_front(); temple(1); temple(-1); }
else if (view == "mount") { mount_printable(); }
else if (view == "plate") {
    translate([0, 0, -vertex]) { frame_front(); }
    translate([0, -60, 0]) rotate([90, 0, 0]) temple(1);
    translate([0, -100, 0]) mount_printable();
}
else if (view == "section") {
    difference() { union() { glasses(); eyes(); fov_cone(); }
                   translate([-200, 0.0, -100]) cube([400, 200, 400]); }
}

// ---------- numbers to read off the render console ----------
p = cam_pos();
echo(camera_position = p, camera_to_pupil_mm = norm([ipd / 2 - p[0], -p[1], -p[2]]));
echo(scene_width_at_pupil_mm = 2 * cam_dist * tan(cam_hfov / 2),
     pupil_px_4mm_at_800 = 4 * 800 / (2 * cam_dist * tan(cam_hfov / 2)));
echo(thermal_block_mass_g = cam_pcb * cam_pcb * sink_t / 1000 * 2.7, "aluminium");
