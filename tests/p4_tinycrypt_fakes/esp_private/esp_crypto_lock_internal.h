#pragma once
#define ECC_RCC_ATOMIC() for (int test_atomic_once = 1; test_atomic_once; test_atomic_once = 0)
