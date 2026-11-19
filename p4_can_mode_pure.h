#pragma once
#include <stdint.h>

// Diagnostic isolation: YL's extra physical CAN2 has no application TX route.
// Retain RX while suppressing ACK/error-frame participation on that bus only.
static inline bool p4CanReceiveOnlyPure(bool yl, uint8_t physicalBus, bool usbPassive) {
  return usbPassive || (yl && physicalBus == 1u);
}
