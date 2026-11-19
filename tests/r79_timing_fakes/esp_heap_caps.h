#pragma once
#include <cstddef>
#include <cstdint>
#define MALLOC_CAP_SPIRAM 0x400u
#define MALLOC_CAP_8BIT 0x4u
void* heap_caps_malloc(size_t, uint32_t);
