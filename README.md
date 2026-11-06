# P4-CAN Universal v3.29.3

S3XY Button Secure Connections / DHKey hotfix for ESP32-P4 post-v3 with an ESP-Hosted ESP32-C6 radio over SDIO. This package starts from `v3.29.1-P4-3TWAI-net2`, explicitly selected by the user. It retains that source's CAN pins, vehicle routes, saved settings and dashboard design. `SOURCE_BASELINE.json` records the original source hashes. The older bundled binary is not reused.

## Preserved wiring

| Physical bus | Controller | TX | RX |
|---|---|---|---|
| CAN 1 BODY | TWAI 0 | GPIO20 | GPIO21 |
| CAN 2 CHASSIS | TWAI 1 | GPIO22 | GPIO23 |
| CAN 3 PARTY | TWAI 2 | GPIO26 | GPIO27 |

All three buses run at 500 kbit/s. Model Y L retains its original internal A=PARTY, B=BODY and extra=CHASSIS routes. Other profiles retain A=BODY, B=CHASSIS and extra=PARTY. The separate net2-pinmap1 mapping is not used.

Hosted SDIO retains CLK18, CMD19, D0=14, D1=15, D2=16, D3=17, RESET54 and GPIO6 as an input. The C6 must already have compatible ESP-Hosted firmware with Bluetooth support. These build tools do not flash either processor.

## P4 ECC repair

The reported `security failed: i=2 e=1291 sm=-1 d=-1` decodes to peer SMP DHKey Check Failed (`0x50b`). It is consistent with Espressif's confirmed ESP-IDF 5.5.5 P4 TinyCrypt defect ([IDF issue 19002](https://github.com/espressif/esp-idf/issues/19002), [Hosted issue 241](https://github.com/espressif/esp-hosted-mcu/issues/241)). The earlier discovery/security scheduling patch did not alter the prebuilt cryptographic implementation.

This package includes all five TinyCrypt ECC/port files from Espressif commit `9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd`, unchanged, under `src/p4_tinycrypt/`. The complete fix preserves native-word/peripheral byte order and sends regularized 257-bit ECDH scalars through the software ladder instead of truncating them in the 256-bit peripheral. The native NimBLE adapter, random key generation, Secure Connections and bonding policy remain in use. The installed SDK and C6 firmware are not modified.

`tools/verify_p4_crypto.py` checks source hashes and actual ELF/map function ownership before the workspace publisher creates artifacts. A known-answer check also exercises the linked NimBLE DHKey API when BLE first starts. A wrong result blocks pairing for that boot and stops the BLE host; `/api/s3xy/stats` exposes `cryptoSelfTestChecked` and `cryptoSelfTestOk`, independently of heavy logging. This is a calculation check, not a substitute for a physical button test.

## BLE changes

- A Pair request interrupts discovery without waiting for the rest of the eight-second window. Discovery still lists multiple candidates when no selection is pending.
- A selected typed address seen within five seconds is reused directly. Missing, unknown or expired addresses use the original fresh target scan.
- A package-local native NimBLE adapter owns authentication before GATT access. It checks the actual encrypted connection state, supports cancellation, and limits its security wait to ten seconds. Arduino's implicit ATT-error reauthentication is disabled while the native bonded Secure Connections / Just Works policy remains enabled.
- A confirmed missing key permits one adapter repair within the same deadline. Unrelated security failures no longer erase the peer's local bond. Explicit Forget and Bluetooth reset keep their existing behavior.
- A host-queue barrier protects scan result lifetimes after discovery ends. A host that does not drain blocks further BLE reuse and unsafe teardown until the barrier completes.
- The existing error display receives initiation, encryption, SMP and disconnection codes. Operational and identity-probe timing/reason telemetry remains available through `/api/s3xy/stats` even when heavy logging is disabled. A value of -1 means no corresponding result was observed.

The SDK's existing connection establishment timeout is retained. The ten-second deadline covers the package-owned security wait; it is not a guarantee for the entire scan/link/GATT workflow or a stalled external transport call.

## Build

Use Arduino-ESP32 3.3.12 with `ESP32P4 Dev Module`, post-v3 silicon, 32 MB flash, `app5M_fat24M_32MB`, enabled PSRAM, Hardware CDC/JTAG and CDC on boot:

```text
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

The editable dashboard is `dashboard_source.html`; regenerate `index_html.h` through `tools/build_dashboard.py`. From this package inside the project workspace, `python3 tools/build_p4.py` invokes the shared publisher and produces the matching OTA BIN/source ZIP under `releases/P4-CAN-Universal-v3.29.3/`. The sketch can also be compiled in Arduino IDE with the board options above; its ELF and map must then pass `python3 tools/verify_p4_crypto.py --elf <build>/<package>.ino.elf` to verify crypto ownership. The source archive includes editable sources, embedded assets, tests and package build tools; build caches are excluded.

## Verification limits

See `VALIDATION.md` and the companion `build-evidence.json` for the actual checks. Host regressions and a target build do not prove a live connection to the reported button, Commander-equivalent pairing speed, C6 coexistence, physical CAN behavior or vehicle operation. No device flash, serial/CAN access or road test is part of this work.
