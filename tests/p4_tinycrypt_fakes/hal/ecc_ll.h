#pragma once
#include <stdbool.h>
static inline void ecc_ll_enable_bus_clock(bool on) { (void)on; }
static inline void ecc_ll_power_up(void) {}
static inline void ecc_ll_power_down(void) {}
static inline void ecc_ll_reset_register(void) {}
