#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef enum { ECC_MODE_VERIFY, ECC_MODE_POINT_MUL, ECC_MODE_VERIFY_THEN_POINT_MUL } ecc_mode_t;
void ecc_hal_write_verify_param(const uint8_t *, const uint8_t *, uint8_t);
void ecc_hal_write_mul_param(const uint8_t *, const uint8_t *, const uint8_t *, uint8_t);
void ecc_hal_set_mode(ecc_mode_t);
void ecc_hal_enable_constant_time_point_mul(bool);
void ecc_hal_start_calc(void);
bool ecc_hal_is_calc_finished(void);
int ecc_hal_read_verify_result(void);
int ecc_hal_read_mul_result(uint8_t *, uint8_t *, uint8_t);
