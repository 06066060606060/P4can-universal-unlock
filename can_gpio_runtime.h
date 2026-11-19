#pragma once
#include <nvs.h>
#include <string.h>
#include "can_error_diag_macros.h"
#include "can_gpio_pure.h"

// Hardware wiring survives feature and BLE-preserving setup resets. Only the
// existing full-partition Factory Reset clears this separate namespace.
static constexpr const char *P4_CAN_GPIO_NAMESPACE = "p4gpio";
static constexpr const char *P4_CAN_GPIO_KEY = "map";
static const char *p4CanGpioLastError = "";
enum P4CanGpioSavedState : uint8_t { P4_GPIO_MISSING, P4_GPIO_VALID, P4_GPIO_CORRUPT, P4_GPIO_READ_ERROR };
struct P4CanGpioStoredRecord {
  bool found = false;
  bool restorable = true;
  size_t size = 0;
  uint8_t bytes[P4_CAN_GPIO_RECORD_SIZE] = {};
};

static bool p4CanGpioReadRecord(P4CanGpioStoredRecord &record) {
  record = {};
  nvs_handle_t handle;
  const esp_err_t open = nvs_open(P4_CAN_GPIO_NAMESPACE, NVS_READONLY, &handle);
  if (open == ESP_ERR_NVS_NOT_FOUND) return true;
  if (open != ESP_OK) return false;
  const esp_err_t sized = nvs_get_blob(handle, P4_CAN_GPIO_KEY, nullptr, &record.size);
  if (sized == ESP_ERR_NVS_NOT_FOUND) { nvs_close(handle); return true; }
  record.found = true;
  if (sized == ESP_ERR_NVS_TYPE_MISMATCH) {
    record.restorable = false;
    nvs_close(handle);
    return true;
  }
  if (sized != ESP_OK) { nvs_close(handle); return false; }
  record.restorable = record.size <= sizeof(record.bytes);
  if (!record.restorable) { nvs_close(handle); return true; }
  size_t copied = record.size;
  const esp_err_t read = nvs_get_blob(handle, P4_CAN_GPIO_KEY, record.bytes, &copied);
  nvs_close(handle);
  return read == ESP_OK && copied == record.size;
}
static P4CanGpioSavedState p4CanGpioReadSaved(P4CanGpioMap &map) {
  P4CanGpioStoredRecord record;
  if (!p4CanGpioReadRecord(record)) return P4_GPIO_READ_ERROR;
  if (!record.found) { map = p4CanGpioDefaultsPure(); return P4_GPIO_MISSING; }
  return record.restorable && p4CanGpioDecodePure(record.bytes, record.size, map)
      ? P4_GPIO_VALID : P4_GPIO_CORRUPT;
}
static P4CanGpioMap p4CanGpioActiveMap() {
  P4CanGpioMap map{};
  for (unsigned bus = 0; bus < 3; ++bus) {
    map.tx[bus] = static_cast<uint8_t>(p4CanTxPins[bus]);
    map.rx[bus] = static_cast<uint8_t>(p4CanRxPins[bus]);
  }
  return map;
}
// The only production writer of effective pins. Call once before installing CAN.
static bool p4CanGpioLoadAtBoot() {
  p4CanGpioValid = false;
  P4CanGpioMap map{};
  const P4CanGpioSavedState state = p4CanGpioReadSaved(map);
  if (state == P4_GPIO_CORRUPT || state == P4_GPIO_READ_ERROR) {
    p4CanGpioLastError = state == P4_GPIO_CORRUPT
        ? "Stored CAN GPIO record is invalid; CAN disabled"
        : "CAN GPIO storage read failed; CAN disabled";
    return false;
  }
  for (unsigned bus = 0; bus < 3; ++bus) {
    p4CanTxPins[bus] = map.tx[bus]; p4CanRxPins[bus] = map.rx[bus];
  }
  p4CanGpioLastError = "";
  p4CanGpioValid = true;
  return true;
}
static bool p4CanGpioWriteRecord(const P4CanGpioStoredRecord &record) {
  if (!record.restorable) return false;
  nvs_handle_t handle;
  if (nvs_open(P4_CAN_GPIO_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return false;
  const esp_err_t changed = record.found
      ? P4_CAN_DIAG_NVS_WRITE(8, nvs_set_blob(handle, P4_CAN_GPIO_KEY, record.bytes, record.size))
      : P4_CAN_DIAG_NVS_WRITE(8, nvs_erase_key(handle, P4_CAN_GPIO_KEY));
  const bool ok = (changed == ESP_OK || (!record.found && changed == ESP_ERR_NVS_NOT_FOUND)) &&
      P4_CAN_DIAG_NVS_WRITE(8, nvs_commit(handle)) == ESP_OK;
  nvs_close(handle);
  return ok;
}
static bool p4CanGpioRecordMatches(const P4CanGpioStoredRecord &expected) {
  P4CanGpioStoredRecord actual;
  return expected.restorable && p4CanGpioReadRecord(actual) && actual.found == expected.found &&
      (!actual.found || (actual.size == expected.size && actual.restorable &&
       memcmp(actual.bytes, expected.bytes, actual.size) == 0));
}
// Maintenance is confirmed by the caller first. Active pins are never changed
// here, including when a successful write needs a later manual reboot.
static bool p4CanGpioPersist(const P4CanGpioMap &map) {
  P4CanGpioStoredRecord candidate;
  candidate.found = true; candidate.size = P4_CAN_GPIO_RECORD_SIZE;
  if (!p4CanGpioEncodePure(map, candidate.bytes, candidate.size)) {
    p4CanGpioLastError = "Invalid CAN GPIO mapping";
    return false;
  }
  P4CanGpioStoredRecord previous;
  if (!p4CanGpioReadRecord(previous)) {
    p4CanGpioLastError = "GPIO save blocked by storage read failure; reboot required";
    return false;
  }
  if (p4CanGpioWriteRecord(candidate) && p4CanGpioRecordMatches(candidate)) {
    p4CanGpioLastError = "";
    return true;
  }
  // Best effort: do not claim preservation unless exact readback confirms it.
  const bool restored = previous.restorable && p4CanGpioWriteRecord(previous) &&
      p4CanGpioRecordMatches(previous);
  p4CanGpioLastError = restored
      ? "GPIO save failed; previous storage verified; CAN stopped, reboot required"
      : "GPIO save failed; storage uncertain; CAN stopped, reboot required";
  return false;
}
