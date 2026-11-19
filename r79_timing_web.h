#pragma once
#include <stdio.h>

// The WebServer task owns these handlers. No network writes occur under the
// journal critical section. A successful enqueue is never physical completion.
static void httpP4R79TimingStatus() {
  const auto s = p4R79TimingSnapshot();
  const uint64_t end = s.active ? (uint64_t)esp_timer_get_time() : s.stopUs;
  const uint64_t elapsed = s.session && end >= s.startUs ? (end - s.startUs) / 1000u : 0u;
  const auto &driver = p4_r79_driver::state;
  char json[1100];
  snprintf(json, sizeof(json),
      "{\"schema\":2,\"fwVersion\":\"%s\",\"active\":%s,\"session\":%lu,"
      "\"count\":%lu,\"capacity\":%lu,\"dropped\":%lu,\"ignoredOldSession\":%lu,"
      "\"startUs\":%llu,\"stopUs\":%llu,\"elapsedMs\":%llu,\"expired\":%s,"
      "\"exporting\":%s,\"allocationFailed\":%s,\"completionMeasured\":false,"
      "\"bootId\":%lu,\"driverErrorLost\":%lu,\"driverSnapshotFailures\":%lu,"
      "\"driverSequenceSaturated\":%s,\"driverImportPending\":%s}",
      FW_VERSION, s.active ? "true" : "false", (unsigned long)s.session,
      (unsigned long)s.count, (unsigned long)s.capacity, (unsigned long)s.dropped,
      (unsigned long)s.ignoredOldSession, (unsigned long long)s.startUs,
      (unsigned long long)s.stopUs, (unsigned long long)elapsed,
      s.expired ? "true" : "false", p4R79TimingExportBusy() ? "true" : "false",
      (p4R79TimingAllocationFailed() || driver.allocationFailed) ? "true" : "false",
      (unsigned long)driver.bootId, (unsigned long)driver.lost,
      (unsigned long)driver.failures, driver.saturated ? "true" : "false",
      driver.pending ? "true" : "false");
  server.send(200, "application/json", json);
}
static void httpP4R79TimingStart() {
  // Preparation and polling belong exclusively to this web task.
  if (!p4R79TimingSnapshot().active && !p4R79TimingExportBusy() &&
      !p4R79TimingDriverPrepare()) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"Driver snapshot or PSRAM unavailable\"}");
    return;
  }
  if (!p4R79TimingStart()) {
    const bool allocation = p4R79TimingAllocationFailed();
    server.send(allocation ? 503 : 409, "application/json",
        allocation ? "{\"ok\":false,\"error\":\"PSRAM allocation failed\"}" :
                     "{\"ok\":false,\"error\":\"Capture or export already active\"}");
    return;
  }
  p4R79TimingDriverStarted();
  httpP4R79TimingStatus();
}
static void httpP4R79TimingStop() {
  p4R79TimingStop();
  p4R79TimingDriverPoll(true);
  httpP4R79TimingStatus();
}
static void httpP4R79TimingCsv() {
  if (p4R79TimingSnapshot().active) {
    server.send(409, "application/json", "{\"ok\":false,\"error\":\"Stop capture before export\"}");
    return;
  }
  p4R79TimingDriverPoll(true);
  p4_r79_timing::Snapshot s = {};
  if (!p4R79TimingBeginExport(s)) {
    server.send(409, "application/json", "{\"ok\":false,\"error\":\"Stop capture before export\"}");
    return;
  }
  struct ExportLease { ~ExportLease() { p4R79TimingEndExport(); } } lease;
  char line[1536];
  const int headerBytes = snprintf(line, sizeof(line),
      "# schema,p4-r79-timing-v2\n# firmware,%s\n# session,%lu\n# start_us,%llu\n"
      "# stop_us,%llu\n# dropped,%lu\n# ignored_old_session,%lu\n# expired,%u\n"
      "# timestamp,R79=task dequeue/enqueue; CAN_ERROR=ISR service; not wire SOF/EOF or ECU acceptance\n"
      "# TX_ACCEPTED,driver enqueue only; physical completion not measured\n"
      "# bus,0=%s 1=%s 2=%s\n"
      "# boot_id,%lu\n# driver_error_lost_upper_bound,%lu\n# driver_snapshot_failures,%lu\n"
      "# driver_sequence_saturated,%u\n# driver_import_pending,%u\n"
      "# ordering,insertion sequence; sort observed_us; CAN_ERROR uses ISR time; imported_us is web-task copy time\n"
      "# rx_reference,latest recorded same-bus/mux RX; not a causal template guarantee; zero=unavailable\n"
      "# ready_mask,bits0-2=CAN1-3 online bit3=extra received since init; adjacent software observation\n",
      FW_VERSION, (unsigned long)s.session, (unsigned long long)s.startUs,
      (unsigned long long)s.stopUs, (unsigned long)s.dropped,
      (unsigned long)s.ignoredOldSession, s.expired ? 1u : 0u,
      p4CanRoleName(0), p4CanRoleName(1), p4CanRoleName(2),
      (unsigned long)p4_r79_driver::state.bootId,
      (unsigned long)p4_r79_driver::state.lost,
      (unsigned long)p4_r79_driver::state.failures,
      p4_r79_driver::state.saturated ? 1u : 0u,
      p4_r79_driver::state.pending ? 1u : 0u);
  if (headerBytes < 0 || (size_t)headerBytes >= sizeof(line)) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"CSV metadata overflow\"}");
    return;
  }
  server.sendHeader("Content-Disposition", "attachment; filename=P4_R79_Timing.csv");
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "text/csv", "");
  server.sendContent(line);
  server.sendContent("session,event_seq,observed_us,elapsed_us,stage,bus,mux,call_id,call_started_us,wait_ticks,result,dlc,data_hex,rx_event_seq,rx_observed_us,rx_to_event_us,driver_call_us,gate_reason,ready_mask,imported_us,error_seq,ecc,tec,rec,status\n");
  for (uint32_t i = 0; i < s.count && server.client().connected(); ++i) {
    p4_r79_timing::Event e = {};
    if (!p4R79TimingRead(i, e)) break;
    char payload[17];
    for (uint8_t j = 0; j < 8; ++j) snprintf(payload + j * 2, 3, "%02X", (unsigned)e.data[j]);
    snprintf(line, sizeof(line), "%lu,%lu,%llu,%llu,%s,%u,%u,%lu,%llu,%lu,%ld,%u,%s,%lu,%llu,%llu,%llu,%s,%lu,%llu,%lu,%lu,%lu,%lu,%lu\n",
        (unsigned long)s.session, (unsigned long)e.sequence, (unsigned long long)e.timeUs,
        (unsigned long long)(e.timeUs - s.startUs), p4R79TimingStageName(e.kind),
        (unsigned)e.bus, (unsigned)e.mux, (unsigned long)e.callId,
        (unsigned long long)e.callUs, (unsigned long)e.waitTicks, (long)e.result,
        (unsigned)e.dlc, payload,
        (unsigned long)e.rxSequence, (unsigned long long)e.rxUs,
        (unsigned long long)(e.rxSequence && e.timeUs >= e.rxUs ? e.timeUs - e.rxUs : 0),
        (unsigned long long)(e.callId && e.callUs && e.timeUs >= e.callUs ? e.timeUs - e.callUs : 0),
        p4_r79_timing::reasonName(e.reason), (unsigned long)e.readyMask,
        (unsigned long long)e.importedUs, (unsigned long)e.errorSeq,
        (unsigned long)e.ecc, (unsigned long)e.tec, (unsigned long)e.rec,
        (unsigned long)e.status);
    server.sendContent(line);
  }
  server.sendContent("");
}
