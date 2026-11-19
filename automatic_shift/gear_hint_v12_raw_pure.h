#pragma once
#include <stdint.h>
#include <string.h>

// Passive acquisition only. SDI bit fields/enums below are from the public
// joshwardell/model3dbc reference, not validated target-vehicle geometry/health.
// Raw bytes are not distances or control permissions. The separate display-only
// experiment validates reference inputs; it never consumes offline fixtures.
namespace gearhintv12 {
constexpr uint8_t kBusCount = 3;
constexpr uint8_t kIdCount = 15;
constexpr uint16_t kHistoryCapacity = 512;
constexpr uint16_t kPageLimit = 128;
constexpr uint16_t kIds[kIdCount] = {
    0x118, 0x20E, 0x22E, 0x30E, 0x32E, 0x33E, 0x34E, 0x35E, 0x39E,
    0x145, 0x3C2, 0x257, 0x129, 0x102, 0x103};
// SDI/gear from the public reference; legacy PARK lengths from the supplied
// 2026-11-16 vehicle log. These are comparison hints, not validity checks.
constexpr uint8_t kReferenceDlcs[kIdCount] = {8, 8, 8, 8, 5, 5, 5, 5, 6, 8, 8, 8, 8, 8, 8};
inline const char *candidateName(uint8_t i) {
  static const char *const names[kIdCount] = {"gear118", "PARK_sdiFront", "PARK_sdiRear",
      "PARK_status2", "PARK_sensorStatusFront", "PARK_sensorStatusRear",
      "PARK_pasFrontMiddle", "PARK_pasRearMiddle", "PARK_pasSides",
      "ESP_status", "VCLEFT_switchStatus", "DI_speed", "SCCM_steeringAngleSensor",
      "VCLEFT_doorStatus", "VCRIGHT_doorStatus"};
  return i < kIdCount ? names[i] : "UNKNOWN";
}
inline int idIndex(uint32_t id) {
  for (uint8_t i = 0; i < kIdCount; ++i) if (id == kIds[i]) return i;
  return -1;
}
inline bool accepts(uint8_t bus, uint32_t id) {
  return bus < kBusCount && idIndex(id) >= 0 && (id != 0x118 || bus == 1);
}
struct Frame {
  uint32_t sequence = 0, observedMs = 0;
  uint8_t bus = 0, idIndex = 0, dlc = 0, data[8] = {};
};
struct Latest {
  Frame frame;
  uint32_t count = 0;
};
inline bool referenceSdiRaw(const Frame &f, uint16_t (&raw)[6]) {
  if (f.bus != 1 || f.idIndex >= kIdCount ||
      (kIds[f.idIndex] != 0x20E && kIds[f.idIndex] != 0x22E) || f.dlc != 8)
    return false;
  uint64_t word = 0;
  for (uint8_t i = 0; i < 7; ++i) word |= static_cast<uint64_t>(f.data[i]) << (8 * i);
  for (uint8_t i = 0; i < 6; ++i) raw[i] = (word >> (9 * i)) & 0x1ff;
  return true;
}
inline int referenceGearRaw(const Frame &f) {
  return f.bus == 1 && f.idIndex < kIdCount && kIds[f.idIndex] == 0x118 && f.dlc == 8
      ? f.data[2] >> 5 : -1;
}
inline int referenceDriverBrakeRaw(const Frame &f) {
  return f.bus == 1 && f.idIndex < kIdCount && kIds[f.idIndex] == 0x145 && f.dlc == 8
      ? (f.data[3] >> 5) & 3 : -1;
}
inline int referenceBrakeApplyRaw(const Frame &f) {
  return referenceDriverBrakeRaw(f) >= 0 ? (f.data[3] >> 7) & 1 : -1;
}
inline int referenceBuckleRaw(const Frame &f) {
  return f.bus < kBusCount && f.idIndex < kIdCount && kIds[f.idIndex] == 0x3C2 &&
      f.dlc == 8 && (f.data[0] & 3) == 0 ? f.data[6] & 3 : -1;
}
struct HistoryPage { uint16_t start = 0, count = 0; bool hasMore = false; };
struct RawObserver {
  Latest latest[kBusCount][kIdCount] = {};
  Latest buckleMux0[kBusCount] = {};
  Frame history[kHistoryCapacity] = {};
  uint32_t sequence = 0, epoch = 0, overwritten = 0;
  uint16_t next = 0, size = 0;

  void reset() {
    // Do not create a whole-ring temporary on an ESP task's small stack.
    memset(static_cast<void *>(latest), 0, sizeof(latest));
    memset(static_cast<void *>(buckleMux0), 0, sizeof(buckleMux0));
    memset(static_cast<void *>(history), 0, sizeof(history));
    sequence = 0; overwritten = 0; next = 0; size = 0; ++epoch;
  }
  void observe(uint8_t bus, uint32_t id, uint8_t dlc, bool extended,
               bool remote, const uint8_t *data, uint32_t now) {
    const int index = idIndex(id);
    if (!accepts(bus, id) || index < 0 || extended || remote ||
        dlc > 8 || (dlc && !data)) return;
    Frame f;
    f.sequence = ++sequence;
    f.observedMs = now; f.bus = bus; f.idIndex = static_cast<uint8_t>(index);
    f.dlc = dlc;
    if (dlc) memcpy(f.data, data, dlc);
    Latest &s = latest[bus][index];
    ++s.count; s.frame = f;
    if (id == 0x3C2) {
      if (referenceBuckleRaw(f) >= 0) {
        ++buckleMux0[bus].count; buckleMux0[bus].frame = f;
      } else if (dlc == 0 || (data[0] & 3) == 0) buckleMux0[bus] = {};
    }
    history[next] = f;
    next = (next + 1) % kHistoryCapacity;
    if (size < kHistoryCapacity) ++size;
    else ++overwritten;
  }
  const Frame &ordered(uint16_t i) const {
    return history[(next + kHistoryCapacity - size + i) % kHistoryCapacity];
  }
  HistoryPage page(bool cursorValid, uint32_t after) const {
    HistoryPage p;
    while (cursorValid && p.start < size &&
        static_cast<int32_t>(ordered(p.start).sequence - after) <= 0) ++p.start;
    const uint16_t available = size - p.start;
    p.count = available > kPageLimit ? kPageLimit : available;
    p.hasMore = available > p.count;
    return p;
  }
};
}  // namespace gearhintv12
