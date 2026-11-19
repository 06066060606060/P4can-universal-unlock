// Mutation target: dropping an initial physical-bus status loses baseline evidence.
#include <cassert>
#include <cstdint>
#include <cstdio>
#if __has_include("../can_error_journal_pure.h")
#include "../can_error_journal_pure.h"
#define CAN_DIAG_PRESENT 1
#else
namespace CanDiag {
struct Status { uint32_t state = 0; };
struct Event {};
class Journal {
public:
  void init(uint32_t, uint64_t) {}
  void observeStatus(uint8_t, const Status&, uint32_t, uint64_t) {}
  bool readEvent(uint8_t, uint32_t, Event&) const { return false; }
};
}
#endif
int main() {
  CanDiag::Journal journal;
  journal.init(123, 10);
  CanDiag::Status status = {};
  status.state = 1;
  journal.observeStatus(0, status, 0, 20);
  CanDiag::Event first = {};
  assert(journal.readEvent(0, 0, first) && "initial physical-bus status must retain baseline evidence");
#ifdef CAN_DIAG_PRESENT
  using namespace CanDiag;
  {
    Journal history;
    ReinitEvent entry = {};
    history.observeReinit(1,3,9,1,1);
    assert(!history.readReinit(0,entry));
    history.init(7,1);
    Status st = {}; st.state=STATE_RUNNING; st.busErrors=130;
    history.observeStatus(1,st,0,10);
    history.observeReinit(1,3,9,1,20);
    history.controllerEpoch(1,30);
    history.observeReinit(1,3,9,2,40);
    Snapshot snap={};history.copyHeader(snap,50);
    assert(snap.reinitCount==2&&snap.reinitObserved==2&&snap.reinitOverwritten==0);
    assert(history.readReinit(0,entry)&&entry.observedUs==20&&entry.requestId==1);
    assert(entry.statusValidMask==2&&entry.busErrors[1]==130&&entry.statusObservedUs[1]==10);
    assert(entry.reason==3&&entry.diagnosticReason==9&&entry.phase==1&&entry.controllerEpoch[1]==1);
    assert(history.readReinit(1,entry)&&entry.phase==2&&entry.controllerEpoch[1]==2&&entry.statusValidMask==0);
    for(uint32_t i=2;i<12;++i)history.observeReinit(i,2,4,3,50+i);
    history.copyHeader(snap,70);
    assert(snap.reinitCount==REINIT_CAPACITY&&snap.reinitObserved==12&&snap.reinitOverwritten==4);
    for(uint32_t i=0;i<REINIT_CAPACITY;++i){assert(history.readReinit(i,entry));assert(entry.seq==i+5&&entry.requestId==i+4);}
    assert(!history.readReinit(REINIT_CAPACITY,entry));
    history.observeReinit(99,0,0,0,71);history.observeReinit(99,0,0,4,72);
    history.copyHeader(snap,73);assert(snap.reinitObserved==12);
    history.init(8,100);history.copyHeader(snap,101);
    assert(snap.reinitCount==0&&snap.reinitObserved==0&&!history.readReinit(0,entry));
  }

  assert(first.bus == 0 && first.observedUs == 20 && first.epoch == 1);
  assert(first.statusValid && first.statusObservedUs == 20 && first.reasonMask == BASELINE);
  assert(!journal.bus(0).hasFirstError && !journal.bus(1).hasStatus);
  journal.observeStatus(0, status, 0, 1000019);
  assert(journal.bus(0).count == 1);
  journal.observeStatus(0, status, 0, 1000020);
  assert(journal.readEvent(0, 1, first) && first.reasonMask == PERIODIC);
  status.txPending = 8;
  journal.observeStatus(0, status, 0, 1000021);
  assert(journal.bus(0).count == 3);
  uint8_t data[8] = {0x80,1,2,3,4,5,6,0xff};
  journal.observeTx(0, 0x3fd, 8, data, -7, 4, true, 1000022);
  data[0] = 0;
  journal.observeRx(0, 1000023);
  journal.observeService(0, 1000024);
  journal.observeService(0, 1000029);
  status.txFailed = 3;
  status.busErrors = 2;
  journal.observeStatus(0, status, 0, 1000030);
  assert(journal.readEvent(0, 3, first));
  assert(first.delta.txFailed == 3 && first.delta.busErrors == 2);
  assert(first.tx.id == 0x3fd && first.tx.dlc == 8 && first.tx.result == -7);
  assert(first.tx.data[0] == 0x80 && first.tx.data[7] == 0xff && first.tx.called);
  assert(first.rxSeen && first.rxAgeUs == 7 && first.serviceSeen && first.serviceGapUs == 1);
  assert(journal.bus(0).maxServiceGapUs == 5);
  const Event retainedFirst = journal.bus(0).firstError;
  assert(retainedFirst.observedUs == 1000030);
  // A controller reset establishes a baseline and cannot create UINT32 deltas.
  status.txFailed = status.busErrors = 0;
  journal.observeStatus(0, status, 0, 1000031);
  assert(journal.readEvent(0, 4, first));
  assert((first.reasonMask & COUNTER_RESET) && first.epoch == 2);
  assert(first.delta.txFailed == 0 && first.delta.busErrors == 0);
  assert(journal.bus(0).latestError.seq == retainedFirst.seq);
  status.busErrors = 1;
  journal.observeStatus(0, status, 0, 1000032);
  assert(journal.bus(0).latestError.delta.busErrors == 1);
  journal.controllerEpoch(0, 1000033);
  assert(!journal.bus(0).hasStatus && !journal.bus(0).latestTx.valid);
  status.busErrors = 900;
  journal.observeStatus(0, status, 0, 1000034);
  assert(journal.readEvent(0, journal.bus(0).count - 1, first));
  assert(first.delta.busErrors == 0 && first.epoch == 3 && (first.reasonMask & BASELINE));
  assert(journal.bus(0).latestError.status.busErrors == 1);
  // Arbitration lost is contention, not independent proof of a bus fault.
  Status contention = {};
  contention.state = STATE_RUNNING;
  contention.txFailed = 123; // Nonzero baseline is historic, not a new failure.
  journal.observeStatus(1, contention, 0, 1000035);
  contention.arbLost = 12;
  journal.observeStatus(1, contention, 0, 1000036);
  journal.observeAlerts(1, 0x2, 1000037, 0); // TX success-like alert.
  assert(!journal.bus(1).hasFirstError);
  journal.observeAlerts(1, 0x400, 1000038, 0x400);
  assert(journal.bus(1).firstError.observedUs == 1000038);
  assert(journal.bus(1).firstError.statusObservedUs == 1000036);
  // Recovery acceptance is not evidence that the controller has recovered.
  journal.observeRecovery(1, true, true, 1000039);
  assert(journal.readEvent(1, journal.bus(1).count - 1, first));
  assert((first.reasonMask & RECOVERY_ACCEPTED) && !(first.reasonMask & RECOVERY_RUNNING));
  journal.observeRecovery(1, false, true, 1000040);
  assert(journal.readEvent(1, journal.bus(1).count - 1, first));
  assert(first.reasonMask == RECOVERY_RUNNING);
  // Busy PARTY must not overwrite BODY's retained first-error evidence.
  Status party = {};
  party.state = STATE_RUNNING;
  for (unsigned i = 0; i < 80; ++i) {
    party.txPending = i;
    journal.observeStatus(2, party, 0, 2000000 + i);
  }
  assert(journal.bus(2).count == 32 && journal.bus(2).observed == 80);
  assert(journal.bus(2).overwritten == 48);
  assert(journal.readEvent(2, 0, first) && first.status.txPending == 48);
  assert(journal.readEvent(2, 31, first) && first.status.txPending == 79);
  assert(journal.bus(0).firstError.seq == retainedFirst.seq);
  party.state = STATE_BUS_OFF;
  journal.observeStatus(2, party, 0, 2000100);
  const Event busOff = journal.bus(2).firstBusOff;
  assert(journal.bus(2).hasFirstBusOff && busOff.status.state == 2);
  for (unsigned i = 0; i < 70; ++i) {
    party.txPending = i;
    journal.observeStatus(2, party, 0, 2000200 + i);
  }
  assert(journal.bus(2).firstBusOff.seq == busOff.seq);
  assert(journal.bus(2).firstError.seq == busOff.seq);
  assert(journal.bus(2).latestError.seq != busOff.seq);
  // Backwards software samples are clamped; 64-bit time survives the 32-bit tick wrap.
  party.state = STATE_RUNNING;
  journal.observeStatus(2, party, 0, 1);
  assert(journal.readEvent(2, 31, first) && first.observedUs == 2000269);
  journal.observeService(2, (uint64_t(1) << 32) + 100);
  journal.observeService(2, (uint64_t(2) << 32) + 200);
  assert(journal.bus(2).maxServiceGapUs == UINT32_MAX);
  // An overlapping application NVS window stays active until its final scope exits.
  const uint64_t flashTime = (uint64_t(3) << 32);
  const uint32_t a = journal.flashBegin(1, flashTime);
  const uint32_t b = journal.flashBegin(2, flashTime + 10);
  journal.flashEnd(a, flashTime + 20);
  Snapshot snapshot = {};
  journal.copyHeader(snapshot, flashTime + 20);
  assert(snapshot.flashCurrent.activeCount == 1 && snapshot.flashCurrent.source == 1);
  assert(snapshot.flashCurrent.flags & FLASH_OVERLAPPED);
  journal.observeAlerts(0, 1, flashTime + 21);
  assert(journal.readEvent(0, journal.bus(0).count - 1, first));
  assert(first.flashCurrent.activeCount == 1 && first.flashCurrent.beginUs == flashTime);
  journal.flashEnd(b, flashTime + 30);
  journal.copyHeader(snapshot, flashTime + 30);
  assert(!snapshot.flashCurrent.activeCount && (snapshot.flashLast.flags & FLASH_VALID));
  assert(snapshot.flashLast.beginUs == flashTime && snapshot.flashLast.endUs == flashTime + 30);
  assert(snapshot.flashLast.flags & FLASH_OVERLAPPED);
  // Init and invalid inputs cannot leak an old boot into a new journal.
  journal.observeStatus(3, status, 1, flashTime + 40);
  assert(!journal.readEvent(3, 0, first) && !journal.readEvent(0, 99, first));
  const uint32_t stale = journal.flashBegin(3, flashTime + 50);
  journal.init(456, 0);
  const uint32_t fresh = journal.flashBegin(4, 2);
  journal.flashEnd(stale, 3);
  journal.copyHeader(snapshot, 4);
  assert(snapshot.bootId == 456 && snapshot.flashCurrent.activeCount == 1);
  journal.flashEnd(fresh, 5);
  for (unsigned bus = 0; bus < 3; ++bus) {
    assert(journal.bus(bus).count == 0 && !journal.bus(bus).hasFirstError);
    assert(!journal.bus(bus).hasFirstBusOff && journal.bus(bus).epoch == 1);
  }
#ifdef CAN_DIAG_FLASH_HISTORY
  Journal nvsHistory;
  nvsHistory.init(99, 0);
  for (uint32_t i = 0; i < 40; ++i) {
    const uint32_t token = nvsHistory.flashBegin(uint8_t(i), 100 + i * 10);
    nvsHistory.flashEnd(token, 105 + i * 10);
  }
  nvsHistory.copyHeader(snapshot, 500);
  assert(snapshot.flashCount == 32 && snapshot.flashObserved == 40 && snapshot.flashOverwritten == 8);
  assert(snapshot.flashWindows[0].beginUs == 180 && snapshot.flashWindows[0].endUs == 185);
  assert(snapshot.flashWindows[31].beginUs == 490 && snapshot.flashWindows[31].endUs == 495);
  assert(snapshot.flashWindows[31].seq == snapshot.flashLast.seq);
#else
  assert(false && "completed NVS bursts require bounded exportable window history");
#endif
#ifdef CAN_DIAG_TX_PENDING
  Journal calls;
  calls.init(88, 0);
  const uint8_t frameData[8] = {1,2,3,4,5,6,7,8};
  const uint32_t call1 = calls.txBegin(0, 0x100, 8, frameData, 1, 100);
  const uint32_t call2 = calls.txBegin(0, 0x101, 8, frameData, 2, 101);
  Status failed = {}; failed.state = STATE_BUS_OFF;
  calls.observeStatus(0, failed, 0, 102);
  assert(calls.bus(0).firstBusOff.tx.callId == call2 && calls.bus(0).firstBusOff.tx.resultPending);
  assert(calls.bus(0).firstBusOff.tx.observedUs == 101 && calls.bus(0).firstBusOff.tx.called);
  calls.txEnd(0, call1, -77, 103);
  assert(calls.bus(0).latestTx.callId == call2 && calls.bus(0).latestTx.resultPending);
  assert(calls.bus(0).unmatchedTxResults == 1);
  calls.txEnd(0, call2, -88, 104);
  assert(!calls.bus(0).latestTx.resultPending && calls.bus(0).latestTx.result == -88);
  assert(calls.bus(0).latestTx.resultDelayUs == 3);
  // Retained evidence remains the context known when BUS OFF was observed.
  assert(calls.bus(0).firstBusOff.tx.resultPending);
  const uint32_t call3 = calls.txBegin(0, 0x102, 0, nullptr, 3, 105);
  calls.txEnd(0, call3, 0, 105);
  assert(calls.bus(0).latestTx.resultDelayUs == 0 && !calls.bus(0).latestTx.resultPending);
  const uint32_t staleCall = calls.txBegin(0, 0x103, 8, frameData, 4, 106);
  calls.init(89, 0);
  const uint32_t newCall = calls.txBegin(0, 0x104, 8, frameData, 5, 1);
  calls.txEnd(0, staleCall, -1, 2);
  assert(calls.bus(0).latestTx.callId == newCall && calls.bus(0).latestTx.resultPending);
  assert(calls.txBegin(3, 0, 0, nullptr, 0, 3) == 0);
  calls.txEnd(3, newCall, 0, 3);
  calls.txEnd(0, 0, 0, 3);
#else
  assert(false && "BUS OFF during blocked TX must retain pending submission context");
#endif
#ifdef CAN_DIAG_CAPTURE_INTERVAL
  Journal service;
  service.init(90, 0);
  service.observeService(0, 0);
  service.observeService(0, 49999);
  assert(service.bus(0).count == 0);
  service.observeService(0, 99999);
  assert(service.bus(0).count == 1 && service.readEvent(0, 0, first));
  assert(first.reasonMask == SERVICE_GAP && first.serviceGapUs == 50000);
  assert(!service.bus(0).hasFirstError);
  for (unsigned i = 0; i < 100; ++i) service.observeService(0, 100000 + i);
  assert(service.bus(0).count == 1 && service.bus(0).maxServiceGapUs == 50000);
#else
  assert(false && "service gaps must be retained before the resume heartbeat replaces them");
#endif
  Journal completion;
  completion.init(123, 0);
  Status recovering = {}; recovering.state = STATE_RECOVERING;
  completion.observeStatus(0, recovering, 0, 1);
  recovering.state = STATE_STOPPED;
  completion.observeStatus(0, recovering, 0, 2);
  // A restart API returning success is not a fresh RUNNING observation.
  recovering.state = STATE_BUS_OFF;
  completion.observeStatus(0, recovering, 0, 3);
  assert(completion.readEvent(0, completion.bus(0).count-1, first));
  assert(!(first.reasonMask & RECOVERY_RUNNING));
  recovering.state = STATE_RUNNING;
  completion.observeStatus(0, recovering, 0, 4);
  assert(completion.readEvent(0, completion.bus(0).count-1, first));
  assert((first.reasonMask & RECOVERY_RUNNING) && first.status.state == STATE_RUNNING);
  Journal uninitialized;
  uninitialized.observeStatus(0, status, 1, 1);
  uninitialized.observeTx(0, 1, 8, nullptr, 0, 0, true, 1);
  uninitialized.observeRx(0, 1);
  uninitialized.observeService(0, 1);
  uninitialized.observeAlerts(0, 1, 1, 1);
  uninitialized.controllerEpoch(0, 1);
  uninitialized.observeRecovery(0, true, true, 1);
  assert(!uninitialized.flashBegin(1, 1) && !uninitialized.initialized());
  assert(uninitialized.bus(0).count == 0);
#endif
  std::puts("can_error_journal_pure: PASS");
}
