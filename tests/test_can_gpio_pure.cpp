#include <cassert>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include "can_gpio_pure.h"

int main() {
  const P4CanGpioMap defaults = p4CanGpioDefaultsPure();
  assert(defaults.tx[0] == 20 && defaults.rx[0] == 21);
  assert(defaults.tx[1] == 50 && defaults.rx[1] == 49);
  assert(defaults.tx[2] == 26 && defaults.rx[2] == 27);
  assert(p4CanGpioMapValidPure(defaults));
  for (unsigned pin = 0; pin < 256; ++pin) {
    const bool inUse = pin == 6 || (pin >= 14 && pin <= 19) || pin == 24 || pin == 25 || pin == 54;
    bool expected = pin <= 54 && !inUse;
    assert(p4CanGpioPinAllowedPure(pin) == expected);
  }
  // Exercise every available GPIO as an actual complete checked mapping.
  for (unsigned selected = 0; selected <= 54; ++selected) {
    const bool inUse = selected == 6 || (selected >= 14 && selected <= 19) || selected == 24 || selected == 25 || selected == 54;
    if (inUse) continue;
    P4CanGpioMap expanded{};uint8_t values[6] = {};values[0] = uint8_t(selected);unsigned used=1;
    for (unsigned n=0; used<6; ++n) if (n!=selected && n!=6 && !(n>=14&&n<=19) && n!=24 && n!=25 && n!=54) values[used++]=uint8_t(n);
    for(unsigned bus=0;bus<3;++bus){expanded.tx[bus]=values[bus*2];expanded.rx[bus]=values[bus*2+1];}
    uint8_t bytes[16]{};P4CanGpioMap restored{};
    assert(p4CanGpioMapValidPure(expanded));
    assert(p4CanGpioEncodePure(expanded,bytes,sizeof(bytes)));
    assert(p4CanGpioDecodePure(bytes,sizeof(bytes),restored));
    assert(p4CanGpioMapsEqualPure(expanded,restored));
  }
  auto outOfRange=defaults;outOfRange.tx[0]=55;assert(!p4CanGpioMapValidPure(outOfRange));
  uint8_t pin = 99;
  for (const char *bad : {"", "-20", "+20", " 20", "20 ", "20x", "2.0", "2e1", "256", "4294967316", "99999999999999999999", "\xC2\xB2"}) {
    assert(!p4CanGpioParsePinPure(bad, pin) && pin == 99);
  }
  assert(!p4CanGpioParsePinPure(nullptr, pin));
  assert(p4CanGpioParsePinPure("00020", pin) && pin == 20);
  assert(p4CanGpioParsePinPure("255", pin) && pin == 255);
  auto duplicate = defaults; duplicate.rx[2] = 20;
  assert(!p4CanGpioMapValidPure(duplicate));
  auto reserved = defaults; reserved.rx[2] = 14;
  assert(!p4CanGpioMapValidPure(reserved));
  uint8_t record[P4_CAN_GPIO_RECORD_SIZE] = {};
  assert(p4CanGpioEncodePure(defaults, record, sizeof(record)));
  P4CanGpioMap decoded{};
  assert(p4CanGpioDecodePure(record, sizeof(record), decoded));
  assert(p4CanGpioMapsEqualPure(defaults, decoded));
  for (size_t byte = 0; byte < sizeof(record); ++byte) {
    for (unsigned bit = 0; bit < 8; ++bit) {
      record[byte] ^= 1u << bit;
      assert(!p4CanGpioDecodePure(record, sizeof(record), decoded));
      record[byte] ^= 1u << bit;
    }
  }
  for (size_t size = 0; size < sizeof(record); ++size)
    assert(!p4CanGpioDecodePure(record, size, decoded));
  assert(!p4CanGpioDecodePure(record, sizeof(record) + 1, decoded));
  assert(!p4CanGpioEncodePure(duplicate, record, sizeof(record)));
  assert(!p4CanGpioEncodePure(reserved, record, sizeof(record)));
  assert(!p4CanGpioEncodePure(defaults, record, sizeof(record) - 1));
  assert(!p4CanGpioDecodePure(nullptr, sizeof(record), decoded));
  // Recomputed checksums cannot bless a duplicate, reserved pin or future schema.
  for (unsigned kind = 0; kind < 4; ++kind) {
    assert(p4CanGpioEncodePure(defaults, record, sizeof(record)));
    if (kind == 0) record[11] = 20;
    if (kind == 1) record[11] = 14;
    if (kind == 2) record[4] = 2;
    if (kind == 3) record[5] = 1;
    const uint32_t crc = p4CanGpioCrcPure(record, 12);
    for (unsigned i = 0; i < 4; ++i) record[12 + i] = uint8_t(crc >> (i * 8));
    assert(!p4CanGpioDecodePure(record, sizeof(record), decoded));
  }
  assert(p4CanGpioCrcPure(reinterpret_cast<const uint8_t *>("123456789"), 9) == 0xcbf43926u);
}
