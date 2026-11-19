# SmartShift automatic shifting

Replaces the previous UI_enableSmartShift / BODY 0x334 field override.
Pedal Response and AP Accel / Regen retain their original 0x334 processing.

Source: https://github.com/kl79613/P4Can-automatic-shifting
Commit: c61c90dd40153b62271e524bcd354a75900e9749 (MIT, LICENSE retained).
The four portable core headers are unmodified. Adapted runtime/web files are in
automatic_shift/. Upstream tests use only adjusted include paths.

The service observes the three physical buses and runs on its own 10ms task.
V12 evaluates radar distances; V13/V14 uses the 0x255 + 0x12B candidate pair.
Optional independent confirmations cover D/R manual steering, Park steering and
D/R obstacle steering. Park steering sign calibration is restricted to Model Y
Legacy; choosing V12 does not implicitly calibrate another model.

Requests copy fresh, validated BODY templates: V12 0x229 or V13/V14 0x678.
Preserve source brake, speed, accelerator, doors, seatbelt, template sample count,
cooldown and final confirmation gates. One physical brake press permits at most
one request. Disable/re-enable and CAN recovery retain the consumed brake epoch.
The final application TX mutex serializes execution with recovery/configuration.
Observers/templates and candidate trackers are invalidated on recovery. Passive
mode, administrative hold, unavailable controllers and unsupported BODY-A /
CHASSIS-B routing block execution. Model YL is unsupported by this port.

Settings > SmartShift exposes execution, protocol, speed bus, seatbelt and three
independent steering switches, plus speed thresholds, cooldown, angles and
obstacle distance. Status includes candidate/source, deny reason, template
readiness and request/confirmation/failure counts. It is independent of LAB.

GET /api/smartshift/stats
POST /api/smartshift/update with one or more fields:
enabled, protocol (AUTO/V12/V13V14), speedBus (0 BODY/1 CHASSIS/2 PARTY),
requireSeatbelt, requireSteering, steeringFallback, parkSteeringFallback,
maxKph (0..8), hardCutKph (1..30, >= maxKph), cooldownMs (0..10000),
pDeg/drDeg/obstacleDeg (1..720), obstacleCm (1..499).

Configuration is stored atomically as a versioned 22-byte blob in
features/autoShiftCfg, with readback verification. Existing reset operations
already clear features. The old features/smartshift word is ignored and cannot
enable actual gear execution. A new installation defaults execution OFF.

Validation: tests/test_automatic_shift_host.py compiles the three upstream core
suites and actual adapted runtime/web under ASan/UBSan, including an observed
V12 brake-triggered request and maintenance/recovery/configuration interlocks.
The standalone demo simulates configuration and status; it does not change gears.

Upstream reports testing primarily on a 2021 radar-equipped Model Y (V12).
This port has not been compiled as full firmware, flashed or tested on a vehicle.
Model 3 and Juniper execution remain unverified; host results do not prove ECU
acceptance or correct vehicle movement.
