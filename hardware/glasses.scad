// Eye-tracking glasses, v2 concept: a tiny camera HEAD at the lower rim on a flex cable, and the USB
// bridge board in a pod on the temple (away from the face). Tethered USB-C. Units: mm.
//
// v1 (25 mm USB dev board hanging off the rim) is in git history. v2 follows what Meta does: only the sensor
// and lens sit at the eye; the heat-making electronics sit elsewhere.
//
// Rendered with OpenSCAD 2021.01. NOT test-printed. Part sizes marked ASSUMED come from vendor listings that
// disagree with each other: measure the real parts and edit the numbers before printing anything.
//
// Coordinates: x = wearer's RIGHT, y = up, z = FORWARD (away from the face). The right eye's corneal apex is
// at (+ipd/2, 0, 0); the left eye at (-ipd/2, 0, 0). Temples run backward (-z) toward the ears.
//
//   view = "assembly"  everything + eye models + camera view cone (default)
//   view = "frame"     printable frame front + temples
//   view = "mount"     printable camera-head cradle (joins the lower rim)
//   view = "pod"       printable pod case (USB board housing) + the aluminium cover beside it
//   view = "plate"     frame + mount + pod laid out for printing
//   view = "section"   assembly with the upper half cut away
// Command line:  openscad -o a.png --camera=45,-20,-20,20,-35,0,330 -D 'view="assembly"' glasses.scad

view = "assembly";

// ---------- face / frame ----------
ipd          = 63;     // pupil distance; change for S/M/L
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

// ---------- camera HEAD (sensor + lens on a flex), ASSUMED sizes ----------
// Candidate: OV9281 module with a 5-pin 1.0 mm FPC sensor head and a separate USB board (listing: 100 mm FPC,
// M12 lens EFL 2.6 mm / 81 deg). An M12 holder is at least 14 mm wide: if the head you receive is that big, set
// head_x/head_y to 14. Meta-class heads are 3-8 mm (OmniVision OVM6211: 3.2 mm cube, 400x400 @120 fps).
head_x       = 10;     // ASSUMED
head_y       = 10;     // ASSUMED
head_z       = 8;      // ASSUMED: sensor board + lens, back to front of lens
cam_hfov     = 81;     // listing, ASSUMED horizontal
flex_w       = 5;      // 5-pin 1.0 mm FPC is about 6 mm wide; 5 here for the picture
flex_t       = 0.3;

// where the head sits relative to the right eye. 24 mm / 50 deg puts it inside the lower rim: about 2 mm below
// the rim and 4 mm in front of it, a bump rather than a box.
cam_dist     = 24;     // lens to pupil: close, so the head tucks into the lower rim
cam_elev     = 50;     // looks UP at the eye by this angle (synthetic test: fine to 50, marginal 55, fails 60)
cam_az       = 0;      // 0 = straight below the eye; +20..30 = from the temple side
cam_x_shift  = 0;

// ---------- IR LEDs: 2 x 850 nm, one each side of the head, inside the cradle ----------
led_dx       = 8.5;    // from the head axis
led_size     = 3;      // 3 x 3 x 1.5 block (ASSUMED 3030-class package)

// ---------- USB bridge pod on the outside of the right temple ----------
pod_board    = [15, 30, 4];      // x(width in y), length along temple, thickness: ASSUMED
pod_wall     = 2;
pod_out      = 9;                // how far the pod stands out from the temple's outer face
cover_t      = 2.5;              // aluminium cover on the outer face: thermal mass + spreader

// ---------- helpers ----------
$fn = 48;
module rrect(w, h, r, t) {
    linear_extrude(height = t) offset(r = r) square([w - 2 * r, h - 2 * r], center = true);
}

module eye(pupil_d = 4) {   // apex at z = 0
    color("white") translate([0, 0, -12]) sphere(d = 24);
    color("lightblue") translate([0, 0, -2.5]) sphere(d = 12);
    color("black") translate([0, 0, -0.2]) cylinder(d = pupil_d, h = 0.4, center = true);
}

function cam_pos() = [ipd / 2 + cam_x_shift + cam_dist * cos(cam_elev) * sin(cam_az),
                      -cam_dist * sin(cam_elev),
                      cam_dist * cos(cam_elev) * cos(cam_az)];

// rotate children so +z points from the camera toward the right pupil: pitch about x first, then yaw about y
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
            for (s = [-1, 1]) translate([s * (head_w / 2 - 2), 0, vertex - 2]) cube([8, temple_h + 4, front_t + 2], center = true);
        }
        for (s = [-1, 1]) translate([s * ipd / 2, 0, vertex - 1]) rrect(lens_w, lens_h, 11, front_t + 2);
        translate([0, -lens_h / 2 + 2, vertex - 1]) cylinder(d = 14, h = front_t + 2);   // nose cut-out
    }
}

module temple(s) {   // s = +1 right, -1 left. Right one has a groove for the USB cable.
    translate([s * head_w / 2 - (s > 0 ? 0 : temple_w), -temple_h / 2, vertex + 1 - temple_len])
    difference() {
        cube([temple_w, temple_h, temple_len], center = false);
        if (s > 0) translate([temple_w - 2.2, temple_h / 2 - 1.8, -1]) cube([2.4, 3.6, temple_len - 4]);
    }
}

// ---------- camera head + cradle ----------
module head_part() {   // camera coordinates, +z toward the eye
    color("darkgreen") translate([0, 0, -head_z / 2]) cube([head_x, head_y, head_z - 3], center = true);
    color("dimgray") translate([0, 0, -3]) cylinder(d = min(head_x, head_y) - 1.5, h = 3.5);   // lens, front at z = +0.5
    for (s = [-1, 1]) color("firebrick") translate([s * led_dx, 0, -0.75]) cube([led_size, led_size, 1.5], center = true);
}

module cradle_outer() {   // camera coordinates
    translate([0, 0, -head_z - 1.5]) rrect(2 * led_dx + led_size + 3, head_y + 3, 2.5, head_z + 1.5 + 1);
}
module cradle_cavities() {
    translate([0, 0, -head_z - 0.5]) rrect(head_x + 0.4, head_y + 0.4, 1, head_z + 3);               // head pocket
    for (s = [-1, 1]) translate([s * led_dx, 0, -2.5]) rrect(led_size + 0.6, led_size + 0.6, 0.6, 5);   // LED windows
    translate([0, head_y / 2, -head_z - 1]) cube([flex_w + 1, 8, 4], center = true);                    // flex exit, rim side
}
module rim_block() {
    translate([ipd / 2 + cam_x_shift, -(lens_h / 2 + rim / 2), vertex + front_t / 2])
        cube([2 * led_dx + led_size + 3, rim, front_t], center = true);
}
module cradle_wedge() {   // hull from the cradle's front slab to the frame's lower rim
    hull() {
        aim_at_pupil() translate([0, 0, -4]) rrect(2 * led_dx + led_size + 3, head_y + 3, 2.5, 4);
        rim_block();
    }
}
module mount_printable() {
    difference() {
        union() { aim_at_pupil() cradle_outer(); cradle_wedge(); }
        aim_at_pupil() cradle_cavities();
    }
}

// ---------- flex cable: head -> along the lower rim -> up the outer rim edge -> pod ----------
function flex_pts() =
    let(p = cam_pos(), u = [0, sin(cam_elev), -cos(cam_elev)])
    [ p - u * (head_z + 1),
      [ipd / 2, -(lens_h / 2 + rim) - 0.2, vertex + front_t + 0.3],
      [ipd / 2 + lens_w / 2 + rim - 4, -(lens_h / 2 + rim) + 6, vertex + front_t + 0.3],
      [head_w / 2 - 2, -2, vertex + front_t + 0.3],
      [head_w / 2 + temple_w + pod_wall + 1, -2, vertex - 4] ];

module flex_cable() {
    P = flex_pts();
    color("orange") for (i = [0 : len(P) - 2]) hull() {
        translate(P[i]) cube([flex_w, flex_w, flex_t], center = true);
        translate(P[i + 1]) cube([flex_w, flex_w, flex_t], center = true);
    }
}
function flex_length() = let(P = flex_pts()) norm(P[1] - P[0]) + norm(P[2] - P[1]) + norm(P[3] - P[2]) + norm(P[4] - P[3]);

// ---------- pod (USB bridge board) on the outside of the right temple ----------
pod_in  = [pod_board[2] + 1, pod_board[0] + 1, pod_board[1] + 1];            // x, y, z inner size
pod_x0  = head_w / 2 + temple_w;                                              // outer face of the temple
pod_z0  = vertex - 2 - (pod_board[1] + 1 + 2 * pod_wall);                     // front of the pod sits behind the frame end piece

module pod_case() {
    difference() {
        translate([pod_x0, -(pod_in[1] + 2 * pod_wall) / 2, pod_z0]) cube([pod_in[0] + pod_wall, pod_in[1] + 2 * pod_wall, pod_in[2] + 2 * pod_wall]);
        translate([pod_x0 - 0.1, -pod_in[1] / 2, pod_z0 + pod_wall]) cube([pod_in[0] + 0.1, pod_in[1], pod_in[2]]);   // pocket, open to the temple side
        // flex enters from the front, USB-C cable leaves at the back (into the temple groove)
        translate([pod_x0 + 2, 0, pod_z0 + pod_in[2] + 2 * pod_wall]) cube([8, 8, 2 * pod_wall + 1], center = true);
        translate([pod_x0 + 2, 0, pod_z0]) cube([8, flex_w + 2, 2 * pod_wall + 1], center = true);
    }
}
module pod_cover() {   // aluminium plate on the outer face
    color("silver") translate([pod_x0 + pod_in[0] + pod_wall, -(pod_in[1] + 2 * pod_wall) / 2, pod_z0])
        cube([cover_t, pod_in[1] + 2 * pod_wall, pod_in[2] + 2 * pod_wall]);
}
module pod_board_model() {
    color("darkgreen") translate([pod_x0 + 0.5, -pod_board[0] / 2, pod_z0 + pod_wall + 0.5]) cube([pod_board[2], pod_board[0], pod_board[1]]);
}

// ---------- camera view cone ----------
module fov_cone() {
    L = cam_dist + 15;
    color("yellow", 0.12) aim_at_pupil() hull() {
        cube([0.1, 0.1, 0.1], center = true);
        translate([0, 0, L]) cube([2 * L * tan(cam_hfov / 2), 1.5 * L * tan(cam_hfov / 2), 0.1], center = true);
    }
}

// ---------- assembly ----------
module glasses() {
    color("slategray") frame_front();
    color("slategray") temple(1);
    color("slategray") temple(-1);
    color("steelblue") mount_printable();
    aim_at_pupil() head_part();
    flex_cable();
    color("steelblue") pod_case();
    pod_board_model();
    pod_cover();
}
module eyes() { for (s = [-1, 1]) translate([s * ipd / 2, 0, 0]) eye(); }

if (view == "assembly") { glasses(); eyes(); fov_cone(); }
else if (view == "frame") { frame_front(); temple(1); temple(-1); }
else if (view == "mount") { mount_printable(); }
else if (view == "pod") { pod_case(); translate([0, 0, -50]) pod_cover(); }
else if (view == "plate") {
    translate([0, 0, -vertex]) frame_front();
    translate([0, -60, 0]) rotate([90, 0, 0]) temple(1);
    translate([0, -100, 0]) mount_printable();
    translate([-pod_x0, -140, -pod_z0]) pod_case();
}
else if (view == "section") {
    difference() { union() { glasses(); eyes(); fov_cone(); }
                   translate([-200, 0, -200]) cube([400, 200, 400]); }
}

// ---------- numbers to read off the render console ----------
p = cam_pos();
echo(camera_position = p, camera_to_pupil_mm = norm([ipd / 2 - p[0], -p[1], -p[2]]));
echo(scene_width_at_pupil_mm = 2 * cam_dist * tan(cam_hfov / 2),
     pupil_px_4mm_at_800 = 4 * 800 / (2 * cam_dist * tan(cam_hfov / 2)));
echo(flex_run_mm = flex_length(), flex_listing_mm = 100, "must be <= flex length of the real part");
echo(cover_mass_g = (pod_in[1] + 2 * pod_wall) * (pod_in[2] + 2 * pod_wall) * cover_t / 1000 * 2.7, "aluminium");
