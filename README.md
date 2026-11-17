# P4-CAN Universal Unlock v3.29.3 BETA

The ultimate solution for accessing all features using an ESP32-P4/C6 board + 3 × SN65HVD230 CAN transceivers.

All features of T2CAN-Universal Unlock are included, plus the nag-killer.

**Highlights:**

- Nag-killer
- Advanced EAP (automatically activates the turn signal in NOA)
- EU unlock (bypass R79 EU restrictions)
- Summon Unlock (±85 m) — ESP32-P4 stability fix
- Activate TLSSC if unavailable in your region
- Continuous AP (experimental)
- ISA chime suppression
- Country / Map Region Spoof
- Vision Speed Control Settings
- Pedal map settings
- S3XY Button Bluetooth Support (some fixes still needed)
- Toggle to restore the “Confirm Free Lane Change” setting (doesn't work in the EU; use Auto Blinker)
- Option to disable Driver Monitoring

A valid EAP/FSD subscription is required for some features.

Multiple operating modes supporting five vehicle profiles for Model 3/Y/YL.

**Android mobile dashboard:** [Download the Android APK](https://github.com/06066060606060/t2can-universal-unlock/releases/tag/android_1.2.1)

## Wiring

| Physical bus | Controller | TX | RX |
| --- | --- | --- | --- |
| CAN 1 BODY | TWAI 0 | GPIO20 | GPIO21 |
| CAN 2 CHASSIS | TWAI 1 | GPIO22 | GPIO23 |
| CAN 3 PARTY | TWAI 2 | GPIO26 | GPIO27 |

<p align="center">
  <img width="718" alt="ESP32-P4 wiring diagram" src="https://github.com/user-attachments/assets/7cbf03c8-ebb4-41c9-b624-cad1b8879684">
</p>

## Build

Use Arduino-ESP32 3.3.12 with the following settings:

- Board: `ESP32P4 Dev Module`
- Chip variant: post-v3 silicon
- Flash size: 32 MB
- Partition scheme: `app5M_fat24M_32MB`
- PSRAM: enabled
- USB mode: Hardware CDC/JTAG
- CDC on boot: enabled

```text
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

### Recommended hardware setup

Recommended setup for maximum performance and stability:

- ESP32-P4 + 3 × SN65HVD230
- 120-ohm resistors removed
- High-speed mode enabled

<p align="left">
  <img width="165" alt="SN65HVD230 high-speed mode configuration" src="https://github.com/user-attachments/assets/de1fab24-3905-4dbf-b603-205c5784e361">
   <img width="500" alt="ESP32-P4 board" src="https://github.com/user-attachments/assets/b2f7f3c3-9c50-4bff-a29d-fbed4a528866">
</p>

Hardware links:

- [Amazon — link 1](https://link.amazon/B05fkkBto)
- [Amazon — link 2](https://link.amazon/B0eL8me5V)

### Check your chip revision

Check your ESP32-P4 chip revision and build with correct settings: **V1.X or V3.X**.

<p align="left">
  <img width="295" alt="ESP32-P4 chip revision reference" src="https://github.com/user-attachments/assets/31ea6408-9702-4741-8c8c-eb6e9a7402b7">
   <img width="309" alt="ESP32-P4 revision screenshot" src="https://github.com/user-attachments/assets/fd9561af-b6ea-43ff-9279-cd1bedd10084">
</p>


## ☕ Support the Project

<p align="center">
  <a href="https://tesla-mods.fkey.id/">
    <img height="30" alt="Donate with Crypto" src="https://img.shields.io/badge/Crypto-Donate-F7931A?style=for-the-badge&amp;logo=bitcoin&amp;logoColor=white">
  </a>
  <a href="https://www.paypal.com/donate/?hosted_button_id=Q2YMMMJYTAPJE">
    <img height="30" alt="Donate with PayPal" src="https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&amp;logo=paypal&amp;logoColor=white">
  </a>
  <a href="https://www.buymeacoffee.com/xbmod">
    <img height="30" alt="Buy Me a Coffee" src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png">
  </a>
</p>

<p align="center">
  欢迎请作者喝杯咖啡，助力后续更新～
</p>

<p align="center">
  <img width="279" alt="Donation QR code" src="https://github.com/user-attachments/assets/53b0d528-529d-43f7-bef0-712938274629">
</p>

## Discord

[Join the project Discord server](https://discord.gg/euPbYG8Npc)

## License

GNU GPL v3 or later. See [LICENSE](LICENSE).
