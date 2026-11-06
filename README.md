# P4-CAN Universal Unlock v3.29.3 BETA

All the features of the T2CAN-Universal unlock are included.
https://github.com/06066060606060/t2can-universal-unlock

## wiring
| Physical bus | Controller | TX | RX |
|---|---|---|---|
| CAN 1 BODY | TWAI 0 | GPIO20 | GPIO21 |
| CAN 2 CHASSIS | TWAI 1 | GPIO22 | GPIO23 |
| CAN 3 PARTY | TWAI 2 | GPIO26 | GPIO27 |

## Build

Use Arduino-ESP32 3.3.12 with `ESP32P4 Dev Module`, post-v3 silicon, 32 MB flash, `app5M_fat24M_32MB`, enabled PSRAM, Hardware CDC/JTAG and CDC on boot:

```text
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```


