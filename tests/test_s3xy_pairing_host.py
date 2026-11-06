"""Run production BLE scan/command paths against a deterministic virtual radio.

The device, scan, and clock are external doubles. Queueing, discovery candidate
selection, target matching, and scan lifecycle functions come from s3xy_ble.h.
This proves host scheduling behavior, not physical BLE or Commander latency.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

PACKAGE = Path(os.environ.get("P4_BLE_TEST_PACKAGE", Path(__file__).resolve().parents[1]))


def source_block(source: str, signature: str) -> str:
    """Extract a balanced C++ block, ignoring comments and string literals."""
    start = source.index(signature)
    brace = source.index("{", start)
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    depth = 0
    for match in token.finditer(source, brace):
        if match.group() == "{":
            depth += 1
        elif match.group() == "}":
            depth -= 1
            if depth == 0:
                return source[start : match.end()]
    raise ValueError(f"Unclosed production block: {signature}")


def build_harness(source: str) -> str:
    def block(signature: str) -> str:
        return source_block(source, signature)

    constants = []
    for name in ("S3XY_MAX_DEVICES", "S3XY_DISCOVERY_MAX", "S3XY_LOG_DATA_MAX", "S3XY_PEER_ID_MAX", "S3XY_AUTO_SCAN_SECONDS", "S3XY_DISCOVERY_SCAN_SECONDS"):
        match = re.search(r"static constexpr[^;]*\b" + name + r"\s*=\s*[^;]+;", source)
        if not match:
            raise ValueError(f"Missing production constant: {name}")
        constants.append(match.group())
    types = [block(signature) + ";" for signature in (
        "enum S3xyMapState :", "enum S3xyCommandType :", "enum S3xyScanMode :",
        "enum S3xyLogType :", "struct S3xyDeviceSlot {", "struct S3xyDiscoveredDevice {", "struct S3xyCommandRequest {",
    )]
    production = [block(signature) for signature in (
        "static bool s3xyAddressEquals(", "static int s3xyFindSlotByAddress(",
        "static bool s3xyIsRegisteredAddress(", "static bool s3xyBluetoothMasterIsEnabled(",
        "static void s3xyClearTarget() {", "static void s3xyDiscoveryAdd(",
        "static bool s3xyQueueCommand(", "static bool s3xyTakeCommand(S3xyCommandRequest &out) {",
    )]
    production.append(block("static bool s3xyRuntimeStopIsPending("))
    if "static bool s3xySecurityMayRun(" in source:
        production.append(block("static bool s3xySecurityMayRun("))
    has_handoff = "static bool s3xyUseDiscoveredAddress(" in source
    if has_handoff:
        production.append(block("static bool s3xyUseDiscoveredAddress("))
    feature_flags = "#define HAS_DISCOVERY_HANDOFF " + str(int(has_handoff))
    callback = """
static void deliverAdvert(BLEAdvertisedDevice dev) {
  const uint8_t mode = s3xyScanMode;
  const int8_t slot = s3xyScanSlot;
  const char *target = s3xyScanTargetAddress;
  const char *addr = dev.address.c_str();
  const int16_t rssi = dev.getRSSI();
  const uint8_t addressType = dev.getAddressType();
""" + block("    if (mode == S3XY_SCAN_TARGET && target[0]") + "\n" + block("    if (mode == S3XY_SCAN_DISCOVERY) {") + "\n}\n"
    return "\n\n".join((PREAMBLE, feature_flags, "\n".join(constants), "\n".join(types), GLOBALS, "\n\n".join(production), callback,
        block("static void s3xyDiscoveryScan() {"), block("static bool s3xyScanTargetMode("), SCENARIOS))


PREAMBLE = r'''
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <vector>
#define S3XY_DIAGNOSTICS_ENABLED 0
using String = std::string;
struct BLEClient {};
struct BLERemoteCharacteristic {};
static int criticalDepth = 0;
static int criticalErrors = 0;
static void enterCritical() { ++criticalDepth; }
static void exitCritical() { if (criticalDepth <= 0) ++criticalErrors; --criticalDepth; }
#define portENTER_CRITICAL(x) enterCritical()
#define portEXIT_CRITICAL(x) exitCritical()
static uint32_t clockMs = 0;
static uint32_t millis() { return clockMs; }
struct BLEUUID { explicit BLEUUID(const char *) {} };
struct BLEAdvertisedDevice {
  std::string address = "AA:BB:CC:DD:EE:01";
  std::string name = "ENH_BTN";
  int16_t rssi = -45;
  uint8_t addressType = 1;
  bool service = true;
  std::string getName() const { return name; }
  bool haveServiceUUID() const { return service; }
  bool isAdvertisingService(BLEUUID) const { return service; }
  int getRSSI() const { return rssi; }
  uint8_t getAddressType() const { return addressType; }
};
struct RadioCall { std::string name; int lockDepth; };
static std::vector<RadioCall> radioCalls;
struct ScheduledEvent { uint32_t atMs; std::function<void()> run; };
static std::vector<ScheduledEvent> events;
struct BLEScan {
  bool stopped = false;
  bool active = false;
  bool running = false;
  bool asynchronous = false;
  bool modelFinalCallback = false;
  bool finalCallbackBusy = false;
  bool hostIdleSucceeds = true;
  unsigned starts = 0;
  unsigned stops = 0;
  uint32_t requestedSeconds = 0;
  uint32_t endMs = 0;
  std::vector<ScheduledEvent> pending;
  size_t nextEvent = 0;
  void record(const char *name) { radioCalls.push_back({name, criticalDepth}); }
  void clearResults() {
    record("clearResults");
    if (finalCallbackBusy) {
      std::fputs("ASSERTION: discovery cleared BLE results while the final host callback still owns them\n", stderr);
      std::exit(1);
    }
  }
  void setActiveScan(bool value) { record("setActiveScan"); active = value; }
  bool stop() {
    record("stop"); ++stops; stopped = true; running = false;
    if (asynchronous && modelFinalCallback) finalCallbackBusy = true;
    return true;
  }
  bool isScanning() { record("isScanning"); return running; }
  void begin(uint32_t seconds, bool continuation) {
    record("start"); ++starts; requestedSeconds = seconds; stopped = false; running = true; asynchronous = false;
    if (continuation) { std::fputs("unexpected scan continuation\n", stderr); std::exit(2); }
    endMs = clockMs + seconds * 1000;
    pending = events;
    events.clear();
    nextEvent = 0;
    std::sort(pending.begin(), pending.end(), [](const ScheduledEvent &a, const ScheduledEvent &b) { return a.atMs < b.atMs; });
  }
  void advanceTo(uint32_t until) {
    const uint32_t limit = running ? std::min(until, endMs) : until;
    while (running && nextEvent < pending.size() && pending[nextEvent].atMs <= limit) {
      const auto event = pending[nextEvent++];
      if (event.atMs < clockMs) continue;
      clockMs = event.atMs;
      event.run();
    }
    if (!stopped) clockMs = limit;
    if (clockMs >= endMs) {
      running = false;
      if (asynchronous && modelFinalCallback) finalCallbackBusy = true;
    }
  }
  void start(uint32_t seconds, bool continuation) {
    begin(seconds, continuation);
    advanceTo(endMs);
  }
  bool start(uint32_t seconds, std::nullptr_t, bool continuation) {
    begin(seconds, continuation);
    asynchronous = true;
    return true;
  }
};
static BLEScan radio;
static bool p4BleAwaitHostIdle(uint32_t timeoutMs) {
  radioCalls.push_back({"p4BleAwaitHostIdle", criticalDepth});
  if (!radio.hostIdleSucceeds || (radio.finalCallbackBusy && timeoutMs < 2)) return false;
  if (radio.finalCallbackBusy) {
    clockMs += 2;
    radio.finalCallbackBusy = false;
  }
  return true;
}
#define pdMS_TO_TICKS(ms) (ms)
static void vTaskDelay(uint32_t ticks) {
  radioCalls.push_back({"vTaskDelay", criticalDepth});
  radio.advanceTo(clockMs + ticks);
}
struct BLEDevice {
  static BLEScan *getScan() { radioCalls.push_back({"getScan", criticalDepth}); return &radio; }
};
'''

GLOBALS = r'''
static S3xyDeviceSlot s3xyDevices[S3XY_MAX_DEVICES] = {};
static S3xyDiscoveredDevice s3xyDiscovered[S3XY_DISCOVERY_MAX] = {};
static volatile uint8_t s3xyDiscoveredCount = 0;
static volatile bool s3xyDiscoveryScanning = false;
static char s3xyDiscoveryError[64] = {};
static bool s3xyBluetoothEnabled = true;
static bool s3xyBleInitialized = true;
static bool s3xyRuntimeStopRequested = false;
static bool s3xyRuntimeStopping = false;
static S3xyCommandRequest s3xyCommand = {};
static uint8_t s3xyScanMode = S3XY_SCAN_NONE;
static int8_t s3xyScanSlot = -1;
static char s3xyScanTargetAddress[24] = {};
static bool s3xyScanTargetFound = false;
static BLEAdvertisedDevice *s3xyTarget = nullptr;
static const char *S3XY_SERVICE_UUID = "3D46";
static void s3xyLogPush(uint8_t, const char *) {}
'''

SCENARIOS = r'''
static void require(bool result, const char *message) {
  if (!result) { std::fprintf(stderr, "ASSERTION: %s (clock=%u ms)\n", message, clockMs); std::exit(1); }
}
static void requireRadioOutsideLock() {
  require(criticalDepth == 0 && criticalErrors == 0, "application lock must be balanced");
  for (const auto &call : radioCalls) {
    if (call.lockDepth != 0) {
      std::fprintf(stderr, "ASSERTION: BLE %s called while s3xyMux held\n", call.name.c_str());
      std::exit(1);
    }
  }
}
static void advertiseAt(uint32_t atMs, const char *address, int16_t rssi = -45, uint8_t addressType = 1) {
  BLEAdvertisedDevice dev;
  dev.address = address; dev.rssi = rssi; dev.addressType = addressType;
  events.push_back({atMs, [dev]() { deliverAdvert(dev); }});
}
static void initialState() {
  s3xyBluetoothEnabled = true; s3xyBleInitialized = true;
  s3xyDevices[0].used = true;
  s3xyDevices[0].state = S3XY_MAP_IDLE;
}
int main(int argc, char **argv) {
  require(argc == 2, "one test scenario is required");
  initialState();
  const std::string scenario = argv[1];
#if HAS_DISCOVERY_HANDOFF
  if (scenario.rfind("handoff-", 0) == 0 || scenario == "fresh-handoff")
    std::strcpy(s3xyDevices[0].address, "AA:BB:CC:DD:EE:01");
#endif
  if (scenario == "pair-interrupt") {
    advertiseAt(100, "AA:BB:CC:DD:EE:01");
    events.push_back({205, []() {
      require(s3xyDiscoveryScanning && s3xyDiscoveredCount == 1, "pair request follows a visible candidate during discovery");
      require(s3xyQueueCommand(S3XY_CMD_PAIR_ADDRESS, -1, "AA:BB:CC:DD:EE:01"), "free queue accepts pair request");
    }});
    s3xyDiscoveryScan();
    require(clockMs >= 205 && clockMs <= 215, "accepted Pair must release discovery within one poll instead of waiting for the remaining 8-second window");
    require(!s3xyDiscoveryScanning && s3xyScanMode == S3XY_SCAN_NONE, "interrupted discovery finishes its state transition");
    require(s3xyDiscoveredCount == 1, "candidate list survives scan cancellation");
    S3xyCommandRequest command = {};
    require(s3xyTakeCommand(command), "accepted pair is available to the mapper");
    require(command.type == S3XY_CMD_PAIR_ADDRESS && command.slot == -1 && std::strcmp(command.address, "AA:BB:CC:DD:EE:01") == 0, "mapper receives the selected pair command unchanged");
  } else if (scenario == "discovery-complete-lifetime" || scenario == "discovery-stop-lifetime") {
    radio.modelFinalCallback = true;
    advertiseAt(100, "AA:BB:CC:DD:EE:01");
    if (scenario == "discovery-stop-lifetime") {
      events.push_back({205, []() {
        require(s3xyQueueCommand(S3XY_CMD_PAIR_ADDRESS, -1, "AA:BB:CC:DD:EE:01"), "pair accepted while final callback lifetime is modeled");
      }});
    }
    s3xyDiscoveryScan();
    require(!radio.finalCallbackBusy, "discovery cannot finish until the host completion callback releases scan results");
    require(!s3xyDiscoveryScanning && s3xyScanMode == S3XY_SCAN_NONE, "callback-safe scan teardown restores idle routing");
    require(s3xyDiscoveredCount == 1, "callback-safe teardown preserves the candidate selected by the user");
    require(clockMs <= (scenario == "discovery-stop-lifetime" ? 217U : 8002U), "host callback drain does not restart a discovery or target scan");
  } else if (scenario == "discovery-host-timeout") {
    radio.modelFinalCallback = true;
    radio.hostIdleSucceeds = false;
    s3xyDiscoveryScan();
    require(radio.finalCallbackBusy, "failed host barrier leaves the callback lifetime pending");
    require(s3xyDiscoveryError[0] != '\0', "failed host barrier preserves a user-visible discovery error");
  } else if (scenario == "occupied-queue") {
    require(s3xyQueueCommand(S3XY_CMD_CONNECT_SLOT, 2, "AA:BB:CC:DD:EE:09"), "existing command enters queue");
    advertiseAt(100, "AA:BB:CC:DD:EE:01");
    events.push_back({200, []() {
      require(!s3xyQueueCommand(S3XY_CMD_PAIR_ADDRESS, -1, "AA:BB:CC:DD:EE:01"), "occupied queue rejects pair");
      require(s3xyDiscoveryScanning && radio.stops == 0, "rejected pair leaves discovery running");
    }});
    advertiseAt(7900, "AA:BB:CC:DD:EE:02");
    s3xyDiscoveryScan();
    require(clockMs == 8000 && radio.stops == 0 && s3xyDiscoveredCount == 2, "rejected pair preserves the complete discovery window");
    S3xyCommandRequest command = {};
    require(s3xyTakeCommand(command), "existing command remains available");
    require(command.type == S3XY_CMD_CONNECT_SLOT && command.slot == 2 && std::strcmp(command.address, "AA:BB:CC:DD:EE:09") == 0, "rejected pair cannot overwrite the pending command");
    require(!s3xyTakeCommand(command), "taking the preserved command empties the queue");
  } else if (scenario == "full-discovery") {
    advertiseAt(100, "AA:BB:CC:DD:EE:01");
    advertiseAt(900, "AA:BB:CC:DD:EE:02");
    advertiseAt(7900, "AA:BB:CC:DD:EE:03");
    s3xyDiscoveryScan();
    require(clockMs == 8000 && radio.starts == 1 && radio.stops == 0, "ordinary discovery retains its full 8-second window");
    require(s3xyDiscoveredCount == 3, "ordinary discovery keeps multiple candidates available for user selection");
    require(std::strcmp(s3xyDiscovered[0].address, "AA:BB:CC:DD:EE:01") == 0 && std::strcmp(s3xyDiscovered[2].address, "AA:BB:CC:DD:EE:03") == 0, "early and late candidates remain selectable");
  } else if (scenario == "radio-locks") {
    events.push_back({200, []() { require(s3xyQueueCommand(S3XY_CMD_PAIR_ADDRESS, -1, "AA:BB:CC:DD:EE:01"), "pair accepted for lock validation"); }});
    s3xyDiscoveryScan();
    advertiseAt(clockMs + 100, "AA:BB:CC:DD:EE:01");
    require(s3xyScanTargetMode("AA:BB:CC:DD:EE:01", S3XY_AUTO_SCAN_SECONDS + 2, 0, true), "target scan exercises its stop and cleanup operations");
    require(radio.stops >= 1, "target callback performs its early stop");
  } else if (scenario == "master-off" || scenario == "uninitialized") {
    if (scenario == "master-off") s3xyBluetoothEnabled = false;
    else s3xyBleInitialized = false;
    s3xyDiscoveryScan();
    require(!s3xyDiscoveryScanning && std::strcmp(s3xyDiscoveryError, "Bluetooth is OFF") == 0, "disabled BLE reports discovery unavailable");
    require(!s3xyScanTargetMode("AA:BB:CC:DD:EE:01", S3XY_AUTO_SCAN_SECONDS + 2, 0, true), "disabled BLE blocks target scan");
    require(clockMs == 0 && radioCalls.empty(), "disabled BLE cannot touch the radio or wait for scans");
  } else if (scenario == "target-early") {
    advertiseAt(100, "AA:BB:CC:DD:EE:02");
    advertiseAt(250, "AA:BB:CC:DD:EE:01", -61, 1);
    require(s3xyScanTargetMode("AA:BB:CC:DD:EE:01", S3XY_AUTO_SCAN_SECONDS + 2, 0, false), "target scan ignores other peers and finds the selected address");
    require(clockMs == 250 && radio.stops == 1 && !radio.active, "matching target exits early and preserves requested passive mode");
    require(s3xyTarget && s3xyTarget->address == "AA:BB:CC:DD:EE:01", "connection target is the selected advertisement");
    require(s3xyDevices[0].state == S3XY_MAP_FOUND && s3xyDevices[0].rssi == -61 && s3xyDevices[0].addressTypeKnown && s3xyDevices[0].addressType == 1, "target callback retains connection address metadata");
    require(s3xyScanMode == S3XY_SCAN_NONE && s3xyScanSlot == -1 && s3xyScanTargetAddress[0] == '\0', "target early exit cleans scan routing state");
  } else if (scenario.rfind("target-edge-", 0) == 0) {
    const uint32_t atMs = static_cast<uint32_t>(std::strtoul(scenario.c_str() + 12, nullptr, 10));
    advertiseAt(atMs, "AA:BB:CC:DD:EE:01");
    const bool found = s3xyScanTargetMode("AA:BB:CC:DD:EE:01", S3XY_AUTO_SCAN_SECONDS + 2, 0, true);
    const bool expectedFound = atMs <= 6000;
    require(found == expectedFound, "target scan accepts only advertisements inside its six-second deadline");
    require(clockMs == (expectedFound ? atMs : 6000), "target scan cannot extend its timeout waiting for a late peer");
    require(s3xyDevices[0].state == (expectedFound ? S3XY_MAP_FOUND : S3XY_MAP_IDLE), "target scan reports found or idle at timeout boundary");
    require(s3xyScanMode == S3XY_SCAN_NONE && s3xyScanSlot == -1, "target deadline clears routing state");
  } else if (scenario == "queue-outside-discovery") {
    require(s3xyQueueCommand(S3XY_CMD_PAIR_ADDRESS, -1, "AA:BB:CC:DD:EE:01"), "pair can queue outside discovery");
    require(radioCalls.empty(), "pair queued outside discovery does not stop unrelated scan work");
  } else if (scenario == "runtime-stop" || scenario == "master-off-during-discovery") {
    advertiseAt(100, "AA:BB:CC:DD:EE:01");
    events.push_back({205, [scenario]() {
      if (scenario == "runtime-stop") s3xyRuntimeStopRequested = true;
      else s3xyBluetoothEnabled = false;
    }});
    s3xyDiscoveryScan();
    require(clockMs >= 205 && clockMs <= 215, "runtime stop or master OFF releases discovery within one polling interval");
    require(!s3xyDiscoveryScanning && s3xyScanMode == S3XY_SCAN_NONE, "cancelled discovery clears scan state");
#if HAS_DISCOVERY_HANDOFF
  } else if (scenario == "fresh-handoff") {
    clockMs = 100;
    BLEAdvertisedDevice dev;
    dev.rssi = -67; dev.addressType = 1;
    s3xyScanMode = S3XY_SCAN_DISCOVERY;
    deliverAdvert(dev);
    s3xyScanMode = S3XY_SCAN_NONE;
    clockMs = 200;
    require(s3xyUseDiscoveredAddress("AA:BB:CC:DD:EE:01", 0), "fresh selected discovery candidate avoids another target scan");
    require(radioCalls.empty() && clockMs == 200, "discovery handoff performs no radio operation or delay");
    require(s3xyDevices[0].addressTypeKnown && s3xyDevices[0].addressType == 1, "discovery handoff preserves random/public address type for connection");
  } else if (scenario == "handoff-age-5000" || scenario == "handoff-age-5001") {
    clockMs = 100;
    s3xyDiscoveryAdd("AA:BB:CC:DD:EE:01", "ENH_BTN", -47, 1);
    clockMs = scenario == "handoff-age-5000" ? 5100 : 5101;
    const bool fresh = scenario == "handoff-age-5000";
    require(s3xyUseDiscoveredAddress("AA:BB:CC:DD:EE:01", 0) == fresh, "discovery handoff accepts age 5000ms and rejects age 5001ms");
    require(s3xyDevices[0].addressTypeKnown == fresh, "stale discovery metadata is not adopted");
  } else if (scenario == "handoff-unknown" || scenario == "handoff-invalid" || scenario == "handoff-missing") {
    clockMs = 100;
    if (scenario != "handoff-missing") {
      s3xyDiscoveryAdd("AA:BB:CC:DD:EE:01", "ENH_BTN", -47, 0xff);
      if (scenario == "handoff-invalid") {
        s3xyDiscovered[0].addressType = 0xff;
        s3xyDiscovered[0].addressTypeKnown = true;
      }
    }
    require(!s3xyUseDiscoveredAddress("AA:BB:CC:DD:EE:01", 0), "missing, unknown, or invalid address type requires target rediscovery");
    require(!s3xyDevices[0].addressTypeKnown && radioCalls.empty(), "unusable candidate metadata does not reach the connection slot");
#endif
  } else if (scenario == "other-command") {
    events.push_back({200, []() { require(s3xyQueueCommand(S3XY_CMD_CONNECT_SLOT, 1), "ordinary command accepted during discovery"); }});
    s3xyDiscoveryScan();
    require(clockMs == 8000 && radio.stops == 0, "commands other than Pair preserve the discovery window");
  } else {
    require(false, "unknown test scenario");
  }
  requireRadioOutsideLock();
  s3xyClearTarget();
  std::printf("PASS %s (%u virtual ms)\n", scenario.c_str(), clockMs);
}
'''


class S3xyPairingHostTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="s3xy-pairing-host-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source_path = PACKAGE / "s3xy_ble.h"
        harness = work / "pairing.cpp"
        source = source_path.read_text()
        cls.has_handoff = "static bool s3xyUseDiscoveredAddress(" in source
        harness.write_text(build_harness(source), encoding="utf-8")
        cls.binary = work / "pairing"
        compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
        if not compiler:
            raise RuntimeError("C++ compiler unavailable; host behavior is unverified")
        compiled = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", str(harness), "-o", str(cls.binary)], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError("Production harness did not compile; this is not a behavior RED:\n" + compiled.stdout + compiled.stderr)

    def run_scenario(self, name: str) -> None:
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_accepted_pair_releases_discovery_without_remaining_wait(self):
        self.run_scenario("pair-interrupt")

    def test_completed_discovery_waits_for_host_callback_before_clearing_results(self):
        self.run_scenario("discovery-complete-lifetime")

    def test_interrupted_discovery_waits_for_host_callback_before_clearing_results(self):
        self.run_scenario("discovery-stop-lifetime")

    def test_failed_host_callback_barrier_preserves_pending_results_and_error(self):
        self.run_scenario("discovery-host-timeout")

    def test_occupied_queue_preserves_pending_command_and_discovery(self):
        self.run_scenario("occupied-queue")

    def test_ordinary_discovery_collects_multiple_candidates_for_eight_seconds(self):
        self.run_scenario("full-discovery")

    def test_radio_scan_and_stop_operations_are_outside_s3xy_mux(self):
        self.run_scenario("radio-locks")

    def test_bluetooth_master_off_blocks_scans(self):
        self.run_scenario("master-off")

    def test_uninitialized_ble_blocks_scans(self):
        self.run_scenario("uninitialized")

    def test_target_match_stops_early_and_preserves_address_metadata(self):
        self.run_scenario("target-early")

    def test_target_scan_preserves_six_second_timeout_boundary(self):
        for at_ms in (5999, 6000, 6001):
            with self.subTest(advertisement_at_ms=at_ms):
                self.run_scenario(f"target-edge-{at_ms}")

    def test_pair_outside_discovery_does_not_stop_radio(self):
        self.run_scenario("queue-outside-discovery")

    def test_runtime_stop_interrupts_discovery_within_one_poll(self):
        self.run_scenario("runtime-stop")

    def test_master_off_interrupts_discovery_within_one_poll(self):
        self.run_scenario("master-off-during-discovery")

    def test_fresh_discovery_handoff_avoids_another_radio_scan(self):
        if not self.has_handoff:
            self.skipTest("original baseline has no discovery handoff API")
        self.run_scenario("fresh-handoff")

    def test_discovery_handoff_expires_after_five_seconds(self):
        if not self.has_handoff:
            self.skipTest("original baseline has no discovery handoff API")
        for age_ms in (5000, 5001):
            with self.subTest(candidate_age_ms=age_ms):
                self.run_scenario(f"handoff-age-{age_ms}")

    def test_missing_or_untyped_discovery_candidate_requires_rediscovery(self):
        if not self.has_handoff:
            self.skipTest("original baseline has no discovery handoff API")
        for kind in ("unknown", "invalid", "missing"):
            with self.subTest(candidate=kind):
                self.run_scenario(f"handoff-{kind}")

    def test_other_commands_do_not_interrupt_discovery(self):
        self.run_scenario("other-command")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--package", type=Path)
    options, unittest_args = parser.parse_known_args()
    if options.package:
        PACKAGE = options.package.resolve()
    unittest.main(argv=[__file__, *unittest_args])
