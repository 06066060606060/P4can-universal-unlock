#pragma once
#include <cstdint>
struct twai_message_t { uint32_t identifier; bool extd, rtr; uint8_t data_length_code, data[8]; };
