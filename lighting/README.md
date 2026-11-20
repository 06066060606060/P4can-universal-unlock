# Lighting Features integration

Only AP Forced High Beam and Dynamic Brake Light are active. The pure reference
header is copied unchanged from the user-supplied Desktop/light directory; hashes
and excluded features are recorded in SOURCE.json. The runtime and HTTP adapter
are new files. The original lighting_features.h runtime is not compiled.

AP Forced High Beam is a saved permission, not a saved running state. A valid
BODY 0x249 outward PUSH while AP is fresh (DAS 3/4/5/6, maximum age 3000 ms)
starts the run; a second PUSH stops it. No PUSH replay is available for a stalkless
profile. The runtime strictly rejects missing AP timestamps, unlike the reference
host-harness exception. No beam bits are written on cancellation or AP exit.

Active runs compose BODY 0x3E9 DAS_highLowBeamDecision = 2 (d1 bits3..4)
and clear DAS_ahlbOverride (d3 bit0). A fresh lamp-dark report on BODY 0x3F5 / 0x3F6
can trigger four BODY 0x249 PUSH frames, at least 10 ms apart. Counters and CRCs
advance per accepted frame. Native driver PUSH and normal blinker work take
priority. The reference limits top-ups to eight trains per dark episode, spaced
300 ms apart, and ignores its own PUSH echoes for 700 ms.

Dynamic Brake Light offers Off / Light press / Hard press. It uses the reference
CHASSIS 0x145 (DLC8) and 0x39D (DLC5) pedal decoders and original state machine,
with fresh gear D and speed >8 km/h. Sensor samples expire after 300 ms;
gear/speed expire after 500 ms. It raises only BODY 0x3E9 d2 bit6. On release,
the original received brake bit is restored; the vehicle's own request is preserved.
Hazard and headlight requests in d0 are never changed. Body templates expire
after 1500 ms; stalk templates after 200 ms. Both require valid checksums.

All sends use the final TX barrier and physical BODY bus, respect administrative
hold / passive USB mode / controller availability / recovery epochs / applicable
non-Summon admission, and never mutate a received buffer. Only a successful
enqueue advances TX counters and pending PUSH counts. Settings use the existing
features namespace, key lighting, and are cleared by existing reset operations.
The extra task runs every 5 ms; all three physical RX routes feed the observer.

GET /api/lighting/stats reports settings, AP/run state and enqueue counters.
POST /api/lighting/update accepts apForcedHighBeam=0|1 and/or dynamicBrakeMode=0|1|2.
Malformed values are rejected; unsupported stalk permission requests return 409.

The screenshot's 0x259 conflicts with the supplied implementation: the actual
DAS_bodyControls frame is 0x3E9. Brake bit assignments/thresholds and lamp behavior
are inherited from the supplied reference, whose comments explicitly mark the
pedal mapping as requiring vehicle verification. Local tests prove code behavior,
not vehicle acceptance or physical lamp operation. No firmware build was run.

Host verification (from the project root, Linux/WSL with g++):

```sh
g++ -std=c++17 -Wall -Wextra -Werror -Wno-unused-function -fsanitize=address,undefined -I . tests/test_lighting_runtime.cpp -o /tmp/p4_lighting_test
/tmp/p4_lighting_test
```
