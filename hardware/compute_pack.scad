// Optional v2: wearable compute pack (lanyard / pocket). The glasses stay light: one thin USB-C cable
// to this pack. NOT part of v1 (v1 plugs straight into the laptop). Not rendered yet. Units: mm.
// Sizes are the vendors' published board sizes; the power bank is ASSUMED (check the one you buy).

view = "pack";

pi5_w = 85; pi5_d = 56; pi5_h = 17;     // Raspberry Pi 5 board + active cooler stack (cooler ~ 11 mm over the board)
bank_w = 105; bank_d = 70; bank_h = 18; // ASSUMED slim 10 Ah USB-C PD bank, ~ 200 g
wall = 2.4;
gap = 3;

module box(w, d, h) { translate([-w / 2, -d / 2, 0]) cube([w, d, h]); }

module pack_internals() {
    color("darkgreen") translate([0, 0, 0]) box(pi5_w, pi5_d, pi5_h);                // Pi 5 with cooler
    color("dimgray") translate([0, 0, pi5_h + gap + 1]) box(bank_w, bank_d, bank_h); // battery above it
}

module pack_shell() {
    inner_w = max(pi5_w, bank_w) + 2 * 1; inner_d = max(pi5_d, bank_d) + 2 * 1;
    inner_h = pi5_h + gap + 1 + bank_h + 1;
    difference() {
        translate([-inner_w / 2 - wall, -inner_d / 2 - wall, -wall]) cube([inner_w + 2 * wall, inner_d + 2 * wall, inner_h + 2 * wall]);
        translate([-inner_w / 2, -inner_d / 2, 0]) cube([inner_w, inner_d, inner_h]);
        // intake and exhaust slots for the Pi cooler fan (both long sides, low)
        for (s = [-1, 1]) for (i = [0:5]) translate([-20 + i * 8, s * (inner_d / 2 + 1), 3]) cube([4, wall + 3, 12], center = true);
        // USB-C exit for the glasses cable (short end, low)
        translate([inner_w / 2 + wall / 2, 0, 8]) cube([wall + 2, 12, 7], center = true);
    }
}

if (view == "pack") { color("slategray", 0.35) pack_shell(); pack_internals(); }
else if (view == "internals") { pack_internals(); }

echo(approx_mass_g = "Pi 5 46 + cooler 8 + bank 200 + shell ~60 = ~315 g");
echo(runtime_h_estimate = "10 Ah * 3.7 V = 37 Wh; Pi 5 at 6 W under load -> about 5 h, ASSUMED");
