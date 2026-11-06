#pragma once
#include <cstdint>
#include <cstring>
using esp_err_t = int;
using gpio_num_t = int;
using TickType_t = uint32_t;
constexpr int ESP_OK=0, ESP_FAIL=-1, ESP_ERR_INVALID_ARG=2, ESP_ERR_INVALID_STATE=3, ESP_ERR_TIMEOUT=4;
constexpr int TWAI_MODE_NORMAL=0, TWAI_MODE_LISTEN_ONLY=1;
constexpr int TWAI_STATE_STOPPED=0,TWAI_STATE_RUNNING=1,TWAI_STATE_BUS_OFF=2,TWAI_STATE_RECOVERING=3;
constexpr int TWAI_ALERT_TX_FAILED=1,TWAI_ALERT_ERR_PASS=2,TWAI_ALERT_BUS_ERROR=4,TWAI_ALERT_BUS_OFF=8,TWAI_ALERT_RX_QUEUE_FULL=16;
struct twai_message_t { uint32_t identifier=0; bool extd=false,rtr=false; uint8_t data_length_code=0,data[8]={}; };
struct FakeController { int id,state,mode; bool pending=false; twai_message_t rx; };
using twai_handle_t=FakeController*;
struct twai_general_config_t { int controller_id,tx_io,rx_io,mode; uint32_t rx_queue_len=0,tx_queue_len=0,alerts_enabled=0; };
struct twai_timing_config_t { int bitrate; };
struct twai_filter_config_t { bool acceptAll; };
struct twai_status_info_t {
 int state;
 uint32_t rx_missed_count=0,rx_overrun_count=0,tx_error_counter=0,rx_error_counter=0;
 uint32_t msgs_to_tx=0,msgs_to_rx=0,bus_error_count=0,arb_lost_count=0,tx_failed_count=0;
};
#define TWAI_GENERAL_CONFIG_DEFAULT_V2(id,tx,rx,mode) {id,tx,rx,mode}
#define TWAI_TIMING_CONFIG_500KBITS() {500000}
#define TWAI_FILTER_CONFIG_ACCEPT_ALL() {true}
esp_err_t twai_driver_install_v2(const twai_general_config_t*,const twai_timing_config_t*,const twai_filter_config_t*,twai_handle_t*);
esp_err_t twai_driver_uninstall_v2(twai_handle_t);
esp_err_t twai_start_v2(twai_handle_t);
esp_err_t twai_stop_v2(twai_handle_t);
esp_err_t twai_get_status_info_v2(twai_handle_t,twai_status_info_t*);
esp_err_t twai_receive_v2(twai_handle_t,twai_message_t*,TickType_t);
esp_err_t twai_transmit_v2(twai_handle_t,const twai_message_t*,TickType_t);
