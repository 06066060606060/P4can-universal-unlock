# P4-CAN Universal Unlock 中文说明

[English README](../README.md) | **简体中文**

> 本文是 [P4-CAN Universal Unlock](https://github.com/06066060606060/P4can-universal-unlock) 英文 README 的中文翻译，并补充现有诊断日志导出及问题反馈方法。功能描述以原作者的实际代码、发行说明和更新记录为准。
>
> **兼容性提示：** 原作者明确说明，车辆软件版本早于 **2026.20** 时，项目不能正常工作。

## 项目简介

P4-CAN Universal Unlock 使用 **ESP32-P4/C6 开发板与 3 个 SN65HVD230 CAN 收发器**，为部分 Tesla 车型提供 CAN 通信研究及功能配置能力。

- [英文仪表板模拟](https://06066060606060.github.io/T-Unleash_APP/dashboard_demo.html)
- [中文仪表板模拟](https://06066060606060.github.io/T-Unleash_APP/dashboard_demo.zh-CN.html)

项目支持 Model 3 / Model Y / Model Y L 的五种车辆配置及多种运行模式。部分功能仍需有效的 **EAP/FSD 订阅**，实际可用性受车型、车辆硬件及软件版本影响。

> **安全提示：** 本项目可能与车辆 CAN 控制报文交互。实验性功能并不等于通过车辆功能安全验证。请先在受控环境中验证硬件和只读诊断，不要在公共道路上测试可能影响车辆控制或驾驶员监测的未经验证功能。

## 最近更新

### v3.35.3

- 新增实验性灯光设置（Lighting）。
- 修复 AP 退出并重新进入后，R79 报文注入可能出现的错误。

### v3.35.2

- 新增 CAN GPIO 设置。
- 新增电池预热 Beta 功能。
- 新增实验性 [SmartShift](https://github.com/kl79613/P4Can-automatic-shifting) 功能。
- 新增实验性 FSD 可视化设置；原作者提示该功能可能阻止 AP 激活，并导致部分自动泊车错误。
- 新增 S3XY 按钮的 FSD 可视化动作。
- 新增维护模式（Service Mode）。
- 调整设置页面结构，便于查找功能。
- 新增 S3XY 按钮的 AP 变道动作。
- 新增简体中文固件/界面变体。

更多细节请参阅 [CHANGELOG.md](../CHANGELOG.md)。

## 主要功能

以下名称和功能范围以原作者英文 README 为依据；列出功能不代表全部车型、区域或车机版本均受支持。

- **NAG Killer**：与辅助驾驶方向盘握持提醒相关的功能。
- **Advanced EAP**：在 NOA 场景下自动触发转向灯等相关功能。
- **EU Unlock**：尝试调整欧盟 ECE R79 相关限制。
- **Summon Unlock**：召唤范围调整（原作者标注为 ±85 米，并提及 ESP32-P4 稳定性修复）。
- **TLSSC**：在部分地区提供交通信号灯和停车标志控制的相关设置。
- **Continuous AP**：连续辅助驾驶功能，**实验性**。
- **ISA Chime Suppression**：智能限速辅助提示音设置。
- **Country / Map Region Spoof**：国家或地图区域参数设置。
- **Vision Speed Control Settings**：视觉速度控制设置。
- **Pedal Map Settings**：踏板响应映射设置。
- **S3XY Button Bluetooth Support**：S3XY 蓝牙按钮支持；原作者注明仍有部分问题待修复。
- **Confirm Free Lane Change**：尝试恢复无需确认的变道选项；原作者注明欧盟地区不适用，可考虑 Auto Blinker。
- **Disable Driver Monitoring**：驾驶员监测相关选项。

原作者说明：部分功能需要有效的 EAP/FSD 订阅。

**Android 移动仪表板：** [下载 Android APK](https://github.com/06066060606060/t2can-universal-unlock/releases/tag/android_1.2.1)

## 接线说明（Wiring）

### 普通 Model 3 / Model Y

| 物理 CAN 总线 | 控制器 | TX | RX |
| --- | --- | --- | --- |
| CAN 1 BODY | CAN 1 | GPIO20 | GPIO21 |
| CAN 2 CHASSIS | CAN 2 | GPIO22 | GPIO23 |
| CAN 3 PARTY | CAN 3 | GPIO26 | GPIO27 |

### 2026 年 4 月之后的 Model Y / Model Y L

原作者要求使用 **YL Profile**：

| 物理 CAN 总线 | 控制器 | TX | RX |
| --- | --- | --- | --- |
| CAN 1 VH | CAN 1 | GPIO20 | GPIO21 |
| CAN 2 BODY | CAN 2 | GPIO22 | GPIO23 |
| CAN 3 PARTY | CAN 3 | GPIO26 | GPIO27 |

<img width="300" alt="原作者提供的车辆 CAN 接线示意图" src="https://github.com/user-attachments/assets/68148b49-c256-4757-8ce5-80724e55a58d" />

> **接线前请核对：** 上述表格忠实翻译自英文 README。不过，仓库当前 `pin_config.h` 中 CAN 2 的 TX/RX 定义为 GPIO50/GPIO49，与 README 的 GPIO22/GPIO23 不同。固件也包含 GPIO 设置功能。请先确认实际使用的固件版本与有效引脚映射，再接线；不要仅凭本页接线。

### 推荐硬件配置

原作者推荐：

- ESP32-P4 + **3 × SN65HVD230**。
- 移除相应模块的 **120Ω 终端电阻**。
- 将收发器配置为**高速模式**。

<img width="165" alt="原作者提供的 SN65HVD230 高速模式配置图" src="https://github.com/user-attachments/assets/de1fab24-3905-4dbf-b603-205c5784e361" />
<img width="200" alt="原作者提供的 ESP32-P4 主板照片" src="https://github.com/user-attachments/assets/b2f7f3c3-9c50-4bff-a29d-fbed4a528866" />

> 是否移除终端电阻须结合**实际 CAN 总线拓扑与端接情况**确认。并接到已有正确端接的车辆总线时，不应随意增加终端电阻。

原作者列出的硬件购买参考：

- [Amazon — link 1](https://link.amazon/B05fkkBto)
- [Amazon — link 2](https://link.amazon/B0eL8me5V)

## 固件编译（Build）

使用 **Arduino-ESP32 3.3.12**，原作者列出的设置如下：

| 选项 | 设置 |
| --- | --- |
| Board | `ESP32P4 Dev Module` |
| Chip variant | 按实际芯片修订版本选择 |
| Flash size | 32 MB |
| Partition scheme | 英文 README 列为 `app3M_fat16M_16MB` |
| PSRAM | Enabled |
| USB mode | Hardware CDC/JTAG |
| CDC on boot | Enabled |

原作者提供的 **postv3** 构建标识：

```text
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

**prev3** 构建标识：

```text
esp32:esp32:esp32p4:ChipVariant=prev3,FlashSize=32M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

> **编译前请核对：** 原英文 README 的分区方案列表和两个构建标识并不一致（`fat16M` / `fat9M`）。本翻译保留原文，不自行选择其一；请以正在使用的构建脚本、固件版本和实际 Flash 布局为准。

### 芯片修订版本

请检查 ESP32-P4 实际芯片修订版本，并选择相应构建配置：**V1.X 或 V3.X**。

<img width="150" alt="原作者提供的 ESP32-P4 修订版本参考图" src="https://github.com/user-attachments/assets/31ea6408-9702-4741-8c8c-eb6e9a7402b7" />
<img width="150" alt="原作者提供的芯片修订版本识别截图" src="https://github.com/user-attachments/assets/fd9561af-b6ea-43ff-9279-cd1bedd10084" />

---

## 诊断日志：如何获取并用于 Bug 报告

固件已经提供多种**独立的诊断记录与下载接口**，无需额外安装日志插件。它们的用途不同，不能假设任何一种记录都包含完整车辆 CAN 流量。

### 1. 连接设备并打开诊断页面

1. 启动 P4-CAN，并连接其 Wi-Fi 热点，或通过你已配置的网络访问设备。
2. 在设备使用默认热点 IP 时，浏览器打开 **`http://192.168.4.1`**；若设备网络配置已更改，请使用实际地址。
3. 进入 **设置（Settings）→ 诊断 / 恢复（Diagnostics / Recovery）**。
4. 找到 **下载（Downloads）** 区域，选择与问题相关的日志。

### 2. 下载常见诊断日志

| 页面按钮 | 文件 / API | 适合排查的问题 |
| --- | --- | --- |
| **统计 JSON** | `/api/system/stats` | 固件、运行时间、内存、任务与 CAN 状态 |
| **启动 CSV** | `/api/system/boot-capture.csv` | 启动、初始化、重连与恢复时间线 |
| **CAN 错误 JSON** | `/api/system/can-errors.json` | BUS-OFF、通信错误、控制器恢复异常 |
| **路由 A TX CSV** | `/api/system/cana-tx.csv` | 路由 A 的发送记录 |
| **路由 B TX CSV** | `/api/system/canb-tx.csv` | 路由 B 的发送记录 |
| **BLE CSV** | `/api/s3xy/log.csv` | S3XY 蓝牙连接、按键及通信异常 |

这些地址是**设备自身的 HTTP 接口路径**。例如，使用默认 IP 时，启动记录地址为：

`http://192.168.4.1/api/system/boot-capture.csv`

> 下载的是对应模块的诊断信息；**TX CSV 并非所有物理 CAN 总线的完整报文抓包**，也不保证车辆 ECU 实际接收了每条报文。

### 3. CAN 研究记录（CAN Research Capture）

对于需要观察 CAN 状态变化的问题：

1. 打开 **设置 → CAN 研究记录**。
2. 选择 **SNAPSHOT**（状态快照）或 **RAW TRANSITION**（原始接收报文转换记录）。
3. 可根据需要设置 PRE（事件发生前）及 POST（事件发生后）时间窗口。
4. 在 A / B / C / D 标签栏填写简短、明确的问题标记，例如 `CAN_RECOVERY_01`。
5. 按下相应 **Capture** 按钮，按记录模式进行捕获。
6. 完成后点击 **下载研究记录 CSV（Download Research CSV）**。

接口：`/api/researchcapture/log.csv`

这一采集器为**接收侧诊断用途**，不会因为启用采集而主动发送 CAN 报文。其可用性和容量受固件资源、配置及工作模式限制。

### 4. R79 专项时序记录

如果问题涉及 R79 的状态或时序，并且当前固件界面显示相应选项，可以通过 **R79 Timing** 相关区域使用 **开始记录 10 分钟 / 停止 / 下载 CSV**。

接口：`/api/r79/timing/csv`

### 5. 什么时候导出日志？

- 记录**问题发生的准确时间**（包括时区），如果不能确定，至少记录尽量小的时间范围。
- 同时记录设备的 **Uptime（开机运行时间）**；不少诊断条目按开机后的相对时间计算。
- **问题出现后优先导出日志，再重启设备**。部分记录只保存在 RAM 中，重启后会丢失。
- 如已经重启、清空统计或没有开启专项采集，请在报告中注明。
- 不要为了获取日志而在公共道路上复现有风险的车辆控制故障。

### 6. 提交 Bug 时建议包含的信息

提交前请先[搜索现有 Issues](https://github.com/06066060606060/P4can-universal-unlock/issues)，避免重复报告。

**建议标题：** `[Bug][v3.35.3][Model Y] 问题摘要`

可参考以下模板：

```text
固件版本：
ESP32-P4 芯片修订版本：
车辆型号 / 年款：
车辆软件版本 / 硬件版本：
选择的车辆 Profile / CAN 配置：
是否修改过固件：

问题发生日期：
准确时间或时间段：
时区：
设备 Uptime（如已知）：

复现步骤：
预期行为：
实际行为：
复现频率：
问题发生后是否重启或重置统计：

附件（按需附上）：
[ ] 系统统计 JSON
[ ] 启动 CSV
[ ] CAN 错误 JSON
[ ] CAN 发送记录 CSV
[ ] CAN 研究记录 CSV
[ ] R79 时序 CSV
[ ] BLE CSV
[ ] 截图 / 视频
[ ] 无法取得日志（请说明原因）
```

**隐私提醒：** 上传前检查日志、截图及视频中是否包含车辆识别码（VIN）、位置数据、网络凭据、蓝牙标识等敏感信息，必要时进行遮盖或删减。不必为了提交 Issue 而公开私人信息。

---

## ☕ 支持项目

以下支持方式及留言来自原作者英文 README：

<a href="https://tesla-mods.fkey.id/"><img height="30" alt="Crypto donation" src="https://img.shields.io/badge/Crypto-Donate-F7931A?style=for-the-badge&amp;logo=bitcoin" /></a>
<a href="https://www.paypal.com/donate?hosted_button_id=Q2YMMMJYTAPJE"><img height="30" alt="PayPal donation" src="https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&amp;logo=paypal" /></a>
<a href="https://www.buymeacoffee.com/xbmod"><img height="30" alt="Buy Me a Coffee" src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" /></a>

> 各位，开发这个很不容易，费了好大劲，请大家适当赞赏，让我有持续更新的动力。

<img width="250" alt="原作者提供的支持项目图片" src="https://github.com/user-attachments/assets/003791f1-f670-44b9-8728-73e8b48a24a6" />

## Discord

[加入 Discord 社区](https://discord.gg/euPbYG8Npc)

## 许可协议

原作者英文 README 标注 **GNU GPL v3 或更高版本**。相关许可事项以原项目实际发布的许可文件及其说明为准。