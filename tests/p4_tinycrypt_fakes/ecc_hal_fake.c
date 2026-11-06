/* Test-only boundary for the ESP ECC peripheral. All cryptographic arithmetic
 * is supplied by independent Python callbacks; no KAT output is hard-coded. */
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include "hal/ecc_hal.h"

typedef int (*mul_callback)(const uint8_t *, const uint8_t *, const uint8_t *,
                            uint8_t *, uint8_t *, uint8_t);
typedef int (*verify_callback)(const uint8_t *, const uint8_t *, uint8_t);
static mul_callback mul_impl;
static verify_callback verify_impl;
static uint8_t k[48], x[48], y[48], rx[48], ry[48], size;
static ecc_mode_t mode;
static int result, lock_depth, mul_calls, verify_calls, constant_time;
void test_set_callbacks(mul_callback mul, verify_callback verify) { mul_impl=mul; verify_impl=verify; }
void test_reset_stats(void) { assert(lock_depth==0); mul_calls=verify_calls=constant_time=0; }
int test_mul_calls(void) { return mul_calls; }
int test_verify_calls(void) { return verify_calls; }
int test_constant_time(void) { return constant_time; }
int test_lock_depth(void) { return lock_depth; }
void esp_crypto_ecc_lock_acquire(void) { assert(lock_depth==0); ++lock_depth; }
void esp_crypto_ecc_lock_release(void) { assert(lock_depth==1); --lock_depth; }
void ecc_hal_write_verify_param(const uint8_t *px, const uint8_t *py, uint8_t len) {
 assert(lock_depth==1 && len<=sizeof(x)); size=len; memcpy(x,px,len); memcpy(y,py,len);
}
void ecc_hal_write_mul_param(const uint8_t *scalar, const uint8_t *px, const uint8_t *py, uint8_t len) {
 ecc_hal_write_verify_param(px,py,len); memcpy(k,scalar,len);
}
void ecc_hal_set_mode(ecc_mode_t value) { mode=value; }
void ecc_hal_enable_constant_time_point_mul(bool on) { constant_time=on; }
void ecc_hal_start_calc(void) {
 assert(lock_depth==1 && mul_impl && verify_impl);
 if (mode==ECC_MODE_VERIFY) { ++verify_calls; result=verify_impl(x,y,size); }
 else { ++mul_calls; result=mul_impl(k,x,y,rx,ry,size); }
}
bool ecc_hal_is_calc_finished(void) { return true; }
int ecc_hal_read_verify_result(void) { return result; }
int ecc_hal_read_mul_result(uint8_t *px, uint8_t *py, uint8_t len) {
 assert(len==size); if (result==0) { memcpy(px,rx,len); memcpy(py,ry,len); } return result;
}
