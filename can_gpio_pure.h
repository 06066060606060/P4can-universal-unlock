#pragma once
#include <stddef.h>
#include <stdint.h>
#include "pin_config.h"

struct P4CanGpioMap {
  uint8_t tx[3];
  uint8_t rx[3];
};
static constexpr unsigned P4_CAN_GPIO_COUNT = 55;
// These are actual concurrent users, not a whitelist of CAN-capable pins.
// Hardware CDC/JTAG is required by this package's sketch/build contract.
static constexpr uint8_t P4_CAN_GPIO_IN_USE[] = {
  HOSTED_C6_BOOT, HOSTED_D0, HOSTED_D1, HOSTED_D2, HOSTED_D3,
  HOSTED_CLK, HOSTED_CMD, 24, 25, HOSTED_RESET
};
#if defined(SOC_GPIO_PIN_COUNT) && defined(SOC_GPIO_VALID_OUTPUT_GPIO_MASK)
static_assert(SOC_GPIO_PIN_COUNT == P4_CAN_GPIO_COUNT &&
    SOC_GPIO_VALID_OUTPUT_GPIO_MASK == ((uint64_t(1) << P4_CAN_GPIO_COUNT) - 1),
    "P4 GPIO range must match the actual SDK input/output capabilities");
#endif
static constexpr size_t P4_CAN_GPIO_RECORD_SIZE = 16;

static inline P4CanGpioMap p4CanGpioDefaultsPure() {
  return {{20, 22, 26}, {21, 23, 27}};
}
static inline bool p4CanGpioPinAllowedPure(unsigned pin) {
  if (pin >= P4_CAN_GPIO_COUNT) return false;
  for (uint8_t inUse : P4_CAN_GPIO_IN_USE) if (pin == inUse) return false;
  return true;
}
static inline bool p4CanGpioMapsEqualPure(const P4CanGpioMap &a, const P4CanGpioMap &b) {
  for (unsigned bus = 0; bus < 3; ++bus)
    if (a.tx[bus] != b.tx[bus] || a.rx[bus] != b.rx[bus]) return false;
  return true;
}
static inline bool p4CanGpioMapValidPure(const P4CanGpioMap &map) {
  uint8_t pins[6] = {map.tx[0], map.rx[0], map.tx[1], map.rx[1], map.tx[2], map.rx[2]};
  for (unsigned i = 0; i < 6; ++i) {
    if (!p4CanGpioPinAllowedPure(pins[i])) return false;
    for (unsigned j = 0; j < i; ++j) if (pins[i] == pins[j]) return false;
  }
  return true;
}
// Parsing never truncates or accepts a numeric prefix, sign, whitespace or UTF-8 digit.
static inline bool p4CanGpioParsePinPure(const char *text, uint8_t &out) {
  if (!text || !*text) return false;
  unsigned value = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9') return false;
    const unsigned digit = static_cast<unsigned>(*text - '0');
    if (value > (255u - digit) / 10u) return false;
    value = value * 10u + digit;
  }
  out = static_cast<uint8_t>(value);
  return true;
}
static inline uint32_t p4CanGpioCrcPure(const uint8_t *bytes, size_t size) {
  uint32_t crc = 0xffffffffu;
  for (size_t i = 0; i < size; ++i) {
    crc ^= bytes[i];
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}
// Explicit bytes avoid padding, native endianness and partial per-pin keys.
static inline bool p4CanGpioEncodePure(const P4CanGpioMap &map, uint8_t *out, size_t size) {
  if (!out || size != P4_CAN_GPIO_RECORD_SIZE || !p4CanGpioMapValidPure(map)) return false;
  out[0] = 'P'; out[1] = '4'; out[2] = 'G'; out[3] = 'P';
  out[4] = 1; out[5] = 0;
  for (unsigned bus = 0; bus < 3; ++bus) {
    out[6 + bus * 2] = map.tx[bus]; out[7 + bus * 2] = map.rx[bus];
  }
  const uint32_t crc = p4CanGpioCrcPure(out, 12);
  for (unsigned i = 0; i < 4; ++i) out[12 + i] = static_cast<uint8_t>(crc >> (i * 8));
  return true;
}
static inline bool p4CanGpioDecodePure(const uint8_t *bytes, size_t size, P4CanGpioMap &out) {
  if (!bytes || size != P4_CAN_GPIO_RECORD_SIZE || bytes[0] != 'P' || bytes[1] != '4' ||
      bytes[2] != 'G' || bytes[3] != 'P' || bytes[4] != 1 || bytes[5] != 0) return false;
  uint32_t stored = 0;
  for (unsigned i = 0; i < 4; ++i) stored |= uint32_t(bytes[12 + i]) << (i * 8);
  if (stored != p4CanGpioCrcPure(bytes, 12)) return false;
  P4CanGpioMap candidate{};
  for (unsigned bus = 0; bus < 3; ++bus) {
    candidate.tx[bus] = bytes[6 + bus * 2]; candidate.rx[bus] = bytes[7 + bus * 2];
  }
  if (!p4CanGpioMapValidPure(candidate)) return false;
  out = candidate;
  return true;
}
