#pragma once
// Waveshare ESP32-P4-WIFI6, P4 revision 3.2, C6 ESP-Hosted over SDIO.
//
// Board wiring variants (select at build time, default is unchanged):
//
//   (default) Upstream/ESP32-P4-WIRING diagram, 3x SN65HVD230:
//       CAN 1 BODY    = GPIO20 / GPIO21
//       CAN 2 CHASSIS = GPIO22 / GPIO23
//       CAN 3 PARTY   = GPIO26 / GPIO27
//
//   P4CAN_BOARD_X179 - "ESP32P4 WIFI6 3CAN" expansion board, X179 harness.
//   Define this macro via build_flags (e.g. -DP4CAN_BOARD_X179) when using
//   that expansion board. Its silkscreen CAN1/CAN2 are swapped relative to
//   the X179 connector, so the macros are mapped BY BUS NAME, not by board
//   silkscreen number, to keep each decoder on the correct vehicle bus:
//       board CAN1 = GPIO2(TX) / GPIO3(RX)  -> X179 13/14 CHASSIS (CH)
//       board CAN2 = GPIO4(TX) / GPIO5(RX)  -> X179  9/10 BODY / VEHICLE (VEH)
//       board CAN3 = GPIO26(TX)/ GPIO27(RX) -> X179  2/3 PARTY / PT
//   GPIO2-5 are free HP GPIOs (TOUCH0-3 / LP_GPIO2-5); keep the default
//   USB_SERIAL_JTAG routing so GPIO2-5 are never claimed by external JTAG.
//   If a harness wires CAN1->9/10 BODY and CAN2->13/14 CHASSIS instead,
//   swap the two TX/RX pairs (BODY=2/3, CHASSIS=4/5).

#if defined(P4CAN_BOARD_X179)
#define CAN_BODY_TX 4
#define CAN_BODY_RX 5
#define CAN_CHASSIS_TX 2
#define CAN_CHASSIS_RX 3
#define CAN_PARTY_TX 26
#define CAN_PARTY_RX 27
#else
#define CAN_BODY_TX 20
#define CAN_BODY_RX 21
#define CAN_CHASSIS_TX 22
#define CAN_CHASSIS_RX 23
#define CAN_PARTY_TX 26
#define CAN_PARTY_RX 27
#endif

// ESP32-C6 (ESP-Hosted over SDIO) - identical for both board variants.
#define HOSTED_CLK 18
#define HOSTED_CMD 19
#define HOSTED_D0 14
#define HOSTED_D1 15
#define HOSTED_D2 16
#define HOSTED_D3 17
#define HOSTED_RESET 54
#define HOSTED_C6_BOOT 6
