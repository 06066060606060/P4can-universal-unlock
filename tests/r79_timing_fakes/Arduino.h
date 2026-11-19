#pragma once
#include <cstdint>
#include <mutex>
struct portMUX_TYPE { std::mutex mutex; };
#define portMUX_INITIALIZER_UNLOCKED {}
extern thread_local unsigned timingLockDepth;
void timingBeforeLock();
static inline void portENTER_CRITICAL(portMUX_TYPE* mux) { timingBeforeLock(); mux->mutex.lock(); ++timingLockDepth; }
static inline void portEXIT_CRITICAL(portMUX_TYPE* mux) { --timingLockDepth; mux->mutex.unlock(); }
