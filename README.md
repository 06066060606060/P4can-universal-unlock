
# P4-CAN Universal Unlock v3.29.3 BETA
The ultimate solution to have all features with one board using the 3 Tesla CAN Bus.    
All the features of the T2CAN-Universal unlock are included + the nag-killer.  

** Highlights:**  
- Nag-killer  
- Advanced EAP (Automatically activates the turn signal in noa)  
- EU unlock (Bypass R79 EU restriction)  
- Summon Unlock (+/-85m)  ESP32-P4 fix stabilty issue  
- Activate Tlssc, if not available in your region  
- Continuous AP  (experimental)  
- ISA chime Suppression  
- Country / Map Region Spoof  
- Vision Speed Control Settings  
- Pedal map settings  
- S3XY Button Bluetooth Support (need some fix)  
- Option to Disable Driver Monitoring  
A valid EAP/FSD subscription is required for some features.  

Multiple operating modes supporting five vehicle profiles Model 3/Y/YL :  

- **Android Mobile dashboard** [Android APK](https://github.com/06066060606060/t2can-universal-unlock/releases/tag/android_1.2.1)  

## wiring
| Physical bus | Controller | TX | RX |
|---|---|---|---|
| CAN 1 BODY | TWAI 0 | GPIO20 | GPIO21 |
| CAN 2 CHASSIS | TWAI 1 | GPIO22 | GPIO23 |
| CAN 3 PARTY | TWAI 2 | GPIO26 | GPIO27 |

<img width="718" height="442" alt="ESP32-P4-WIRING" src="https://github.com/user-attachments/assets/7cbf03c8-ebb4-41c9-b624-cad1b8879684" />

### Optional: "ESP32P4 WIFI6 3CAN" expansion board (X179 harness)

The table above remains the default and is unchanged. If you use the Waveshare
"ESP32P4 WIFI6 3CAN" expansion board with an X179 harness, its silkscreen CAN1/CAN2
are swapped relative to the X179 connector. Build with `-DP4CAN_BOARD_X179` to select
the pin mapping for that board (mapped by bus name, not by silkscreen number):

| Physical bus | Controller | TX | RX |
|---|---|---|---|
| CAN 1 BODY | TWAI 0 | GPIO4 | GPIO5 |
| CAN 2 CHASSIS | TWAI 1 | GPIO2 | GPIO3 |
| CAN 3 PARTY | TWAI 2 | GPIO26 | GPIO27 |

All `HOSTED_*` (ESP32-C6 / SDIO) pins stay the same for both variants.

## Build

Use Arduino-ESP32 3.3.12 with `ESP32P4 Dev Module`, post-v3 silicon, 32 MB flash, `app5M_fat24M_32MB`, enabled PSRAM, Hardware CDC/JTAG and CDC on boot:

```text
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```


Rrecommend setup for max performance and stabilty.  
ESP32-P4 + 3 x SN65HVD230  
with removed 120 ohms resistors & highspeed mode enabled


<img width="165" height="254" alt="highspeed" src="https://github.com/user-attachments/assets/de1fab24-3905-4dbf-b603-205c5784e361" />
<img width="500" height="372" alt="ESP32-P4" src="https://github.com/user-attachments/assets/b2f7f3c3-9c50-4bff-a29d-fbed4a528866" />
  

### ☕ Support the Project 

[![Crypto](https://img.shields.io/badge/Crypto-Donate-F7931A?style=for-the-badge&logo=bitcoin&logoColor=white)](https://tesla-mods.fkey.id/) [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/donate/?hosted_button_id=Q2YMMMJYTAPJE)
<a href="https://www.buymeacoffee.com/xbmod" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" style="height: 30px !important;width: 108px !important;" ></a>

### Discord

Join the project Discord server:

https://discord.gg/euPbYG8Npc
