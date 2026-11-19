#pragma once
#include "gear_hint_display_pure.h"
#include "gear_hint_v12_raw_pure.h"
#include "gear_hint_v12_live_pure.h"
#include "gear_shift_pure.h"

#define P4CAN_GEAR_HINT_DISPLAY 1
static gearhint::DisplayHintObserver gearHintDisplayObserver;
static gearhint::DisplayHintObserver gearHintPrearmVisionObserver = [] {
  gearhint::DisplayHintObserver observer;
  observer.brakeGated = false;
  return observer;
}();
static portMUX_TYPE gearHintDisplayMux = portMUX_INITIALIZER_UNLOCKED;
static gearhintv12::RawObserver gearHintV12RawObserver;
static gearhintv12live::Observer gearHintV12LiveObserver;
static gearshift::TemplateObserver gearShiftTemplateObserver;

// Physical identities are fixed: BODY=0, CHASSIS=1, PARTY=2. This observer is
// independent of the feature A/B routes. It never modifies a receive buffer.
static inline void gearHintDisplayObserveRaw(uint8_t bus, uint32_t id,
    uint8_t dlc, bool extended, bool remote, const uint8_t *data) {
  const bool legacy = (bus == 1 && (id == 0x118 || id == 0x145)) ||
      (bus == 2 && (id == 0x255 || id == 0x12B));
  const bool v12 = gearhintv12::accepts(bus, id);
  const bool shiftTemplate = bus == 0 && (id == 0x229 || id == 0x678);
  if (!legacy && !v12 && !shiftTemplate) return;
  const uint32_t now = static_cast<uint32_t>(millis());
  portENTER_CRITICAL(&gearHintDisplayMux);
  if (legacy) {
    gearHintDisplayObserver.observe(bus, id, dlc, extended, remote, data, now);
    gearHintPrearmVisionObserver.observe(bus, id, dlc, extended, remote, data, now);
  }
  if (v12) gearHintV12RawObserver.observe(bus, id, dlc, extended, remote, data, now);
  if (v12) gearHintV12LiveObserver.observe(bus, id, dlc, extended, remote, data, now);
  if (shiftTemplate) gearShiftTemplateObserver.observe(bus, id, dlc, extended, remote, data, now);
  portEXIT_CRITICAL(&gearHintDisplayMux);
}

static inline void gearHintDisplayInvalidateBus(uint8_t bus) {
  if (bus >= gearhintv12::kBusCount) return;
  portENTER_CRITICAL(&gearHintDisplayMux);
  if (bus == 1 || bus == 2) {
    gearHintDisplayObserver = {};
    gearHintPrearmVisionObserver = {};
    gearHintPrearmVisionObserver.brakeGated = false;
  }
  if (bus == 0) gearShiftTemplateObserver.reset();
  gearHintV12RawObserver.reset();
  gearHintV12LiveObserver.reset();
  portEXIT_CRITICAL(&gearHintDisplayMux);
}
