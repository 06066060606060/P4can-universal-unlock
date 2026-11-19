#ifndef P4_TWAI_ERROR_DECODE_PURE_H
#define P4_TWAI_ERROR_DECODE_PURE_H
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t type;
    uint8_t direction;
    uint8_t segment;
    bool ackError;
} P4TwaiErrorDecoded;

static inline P4TwaiErrorDecoded p4TwaiDecodeError(uint32_t ecc) {
    P4TwaiErrorDecoded out;
    out.type = (uint8_t)((ecc >> 6) & 3u);
    out.direction = (uint8_t)((ecc >> 5) & 1u);
    out.segment = (uint8_t)(ecc & 31u);
    /* Match the pinned SDK: a BIT/FORM/STUFF at ACK is still that error type.
     * CRC_SEQUENCE/CRC_DELIMITER are locations, not standalone CRC diagnoses. */
    out.ackError = out.type == 3 && out.segment == 25;
    return out;
}
static inline const char *p4TwaiErrorTypeLabel(uint8_t type) {
    switch (type) {
        case 0: return "BIT";
        case 1: return "FORM";
        case 2: return "STUFF";
        case 3: return "OTHER";
        default: return "UNKNOWN";
    }
}
static inline const char *p4TwaiErrorDirectionLabel(uint8_t direction) {
    switch (direction) {
        case 0: return "TX";
        case 1: return "RX";
        default: return "UNKNOWN";
    }
}
static inline const char *p4TwaiErrorSegmentLabel(uint8_t segment) {
    /* Arduino-ESP32 3.3.12 P4 SDK hal/twai_ll.h twai_ll_err_seg_t. */
    switch (segment) {
        case 2: return "ID_28_21";
        case 3: return "SOF";
        case 4: return "SRTR";
        case 5: return "IDE";
        case 6: return "ID_20_18";
        case 7: return "ID_17_13";
        case 8: return "CRC_SEQUENCE";
        case 9: return "R0";
        case 10: return "DATA";
        case 11: return "DLC";
        case 12: return "RTR";
        case 13: return "R1";
        case 14: return "ID_4_0";
        case 15: return "ID_12_5";
        case 17: return "ACTIVE_ERROR_FLAG";
        case 18: return "INTERMISSION";
        case 19: return "SUPERPOSED_DOMINANT_BITS";
        case 22: return "PASSIVE_ERROR_FLAG";
        case 23: return "ERROR_DELIMITER";
        case 24: return "CRC_DELIMITER";
        case 25: return "ACK_SLOT";
        case 26: return "EOF";
        case 27: return "ACK_DELIMITER";
        case 28: return "OVERLOAD_FLAG";
        default: return "UNKNOWN";
    }
}
#endif
