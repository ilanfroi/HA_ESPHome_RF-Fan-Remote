# ESP32 CC1101 Ceiling Fan RF Control (ESPHome)

> Full TX+RX control of 433MHz OOK ceiling fans using ESP32-C3 + CC1101 (Ebyte E07-M1101D) via ESPHome and Home Assistant.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ESPHome](https://img.shields.io/badge/ESPHome-2024.x-blue.svg)](https://esphome.io/)
[![Platform](https://img.shields.io/badge/Platform-ESP32--C3-green.svg)](https://www.espressif.com/)

## ✨ Key Features

- **Bidirectional Control** — TX commands to the fan + RX state tracking from the physical remote
- **Half-Duplex on Single Pin** — RadioLib handles TX/RX mode switching on GDO0
- **Complete Protocol Reverse-Engineering** — 30-bit OOK format with even parity bit
- **Multi-Fan Support** — Each fan has a unique 20-bit address prefix
- **Home Assistant Integration** — Full fan entity with speed control, light toggle, direction, natural mode, and timer
- **No Hub Required** — Direct RF communication, no proprietary bridge needed

## 📡 Protocol Overview

The ceiling fan uses a **30-bit OOK (On-Off Keying) protocol** at 433.92 MHz:

```
┌─────────────────────────┬───────────┬────────┐
│   29 Data Bits          │ Parity(1) │  Gap   │
│ [Address 20b][Command 9b]│   Even    │ 7093µs │
└─────────────────────────┴───────────┴────────┘
```

### Bit Encoding

| Bit Value | HIGH Duration | LOW Duration | Total |
|-----------|--------------|--------------|-------|
| `1`       | 1182 µs      | 394 µs       | 1576 µs |
| `0`       | 394 µs       | 1182 µs      | 1576 µs |

### Parity Bit (Bit 30)

The parity bit uses a **trailing pulse** encoding (no LOW period follows):
- **Parity 0** → SHORT pulse (394 µs HIGH)
- **Parity 1** → LONG pulse (1182 µs HIGH)

### Frame Structure

- No sync/preamble pulse
- 30 bits per frame (29 data + 1 even parity)
- **7093 µs** inter-frame gap (silence)
- **10 repetitions** per transmission

> 📖 See [docs/protocol.md](docs/protocol.md) for the complete reverse-engineering documentation and code tables.

## 🔧 Hardware

### Components

| Component | Description |
|-----------|-------------|
| ESP32-C3 Super Mini Plus | Microcontroller with WiFi |
| Ebyte E07-M1101D | CC1101 433MHz RF module (SPI) |

### Wiring

| CC1101 Pin | ESP32-C3 Pin | Function |
|-----------|--------------|----------|
| GDO0      | GPIO2        | TX Data / RX Data (half-duplex) |
| CSN       | GPIO7        | SPI Chip Select |
| SCK       | GPIO4        | SPI Clock |
| MOSI      | GPIO6        | SPI Data In |
| MISO      | GPIO5        | SPI Data Out |
| VCC       | 3.3V         | Power |
| GND       | GND          | Ground |

> ⚠️ The E07-M1101D operates at 3.3V. Do NOT connect to 5V.

## 🏗️ How It Works

### RadioLib Half-Duplex Architecture

This project uses the [esphome-radiolib-cc1101](https://github.com/juanboro/esphome-radiolib-cc1101) external component, which leverages RadioLib for proper CC1101 control.

The CC1101 module handles the 433.92 MHz carrier generation internally. The ESP32 GPIO (GDO0) simply toggles HIGH/LOW for OOK modulation — no PWM carrier needed from the MCU.

**Pin Mode Switching:**
- **TX Mode:** `output + input + pullup + open_drain` (allows RadioLib to drive the pin)
- **RX Mode:** `input + pullup` (listens for incoming signals)

**State Machine:**
```
on_boot → recv()
on_transmit → xmit()
on_complete → recv()
OTA on_begin → standby()
```

### TX Configuration

```yaml
remote_transmitter:
  pin: GPIO2
  carrier_duty_percent: 100%   # OOK = full duty (no PWM)
  carrier_frequency: 0Hz       # CC1101 handles RF carrier
```

Commands are sent as `transmit_raw` with exact microsecond timings (not rc_switch protocols).

### RX Configuration

```yaml
remote_receiver:
  pin: GPIO2
  filter: 200us
  idle: 8000us      # > 7093µs inter-frame gap
  tolerance: 50%
```

RX uses `rc_switch_raw` with protocol 1 and 50% tolerance for reliable reception.

## 🚨 Critical: ESPHome CC1101 TX Bug

**ESPHome's built-in `spi:` + `cc1101:` TX is BROKEN** ([Issue #16876](https://github.com/esphome/issues/issues/16876)).

The bug: `pin_mode()` called during TX setup severs the RMT peripheral's connection to the GPIO pad. The CC1101 configures correctly via SPI, but no signal appears on GDO0.

**Solution:** Use RadioLib's external component which manages pin modes correctly.

## 📦 Dependencies

Add this to your ESPHome config:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/juanboro/esphome-radiolib-cc1101
      ref: main
    components: [radiolib_cc1101]
```

## 🚀 Quick Start

1. **Clone this repo**
2. **Copy** `esphome/bedrooms-rf2.yaml` to your ESPHome config directory
3. **Update** the WiFi credentials and API key placeholders
4. **Flash** to your ESP32-C3
5. **Add** the device in Home Assistant

## 📝 Adding Your Own Fan Codes

### Step 1: Capture Codes from Your Remote

Use the RX configuration to capture raw codes from your physical remote. Check ESPHome logs for received `rc_switch_raw` codes.

### Step 2: Identify the Pattern

- First ~20 bits = fan address (same for all buttons on one remote)
- Last ~9 bits = command (changes per button)
- Bit 30 = even parity of bits 1-29

### Step 3: Calculate Parity & Generate Timings

Use the included Python utility:

```bash
# From binary code (29 bits)
python tools/generate_raw_timings.py --binary "10011001000111011011110010001"

# From decimal code
python tools/generate_raw_timings.py --decimal 320895889
```

### Step 4: Add to ESPHome Config

Copy the generated `transmit_raw` timing array into your YAML button/script.

## 💡 Lessons Learned

### 1. Defective CC1101 Modules
Don't Blame the Hardware Too Quickly — We initially thought the first CC1101 module was defective because the fan didn't respond. After discovering the even parity bit requirement, both modules work perfectly. If your TX reaches other receivers but the target device doesn't respond, the issue is likely in the protocol encoding — not the hardware.
### 2. ESPHome's Built-in CC1101 TX is Broken
Hours were spent debugging SPI configurations before discovering that ESPHome's native `cc1101` platform has a fundamental GPIO/RMT conflict. The RadioLib external component bypasses this entirely. Don't waste time with the built-in approach.

### 3. The Mysterious Parity Bit
Initial captures seemed like 29-bit codes until comparing Broadlink RM4 Pro base64 decodes with known-good transmissions. The 30th bit is an even parity over bits 1-29, encoded as a trailing pulse without a subsequent LOW period.

### 4. rc_switch TX Doesn't Work (But RX Does)
While `rc_switch_raw` with protocol 1 receives codes fine at 50% tolerance, transmitting via rc_switch protocols produces incorrect timing. Always use `transmit_raw` with Broadlink-captured microsecond values.

### 5. Half-Duplex Timing
After TX completes, the system must switch back to RX mode. A slight delay (100ms) between repeated transmissions helps ensure clean transitions.

## 📁 Project Structure

```
├── README.md                      # This file
├── LICENSE                        # MIT License
├── esphome/
│   └── bedrooms-rf2.yaml         # Working ESPHome configuration
├── docs/
│   └── protocol.md               # Detailed protocol documentation
└── tools/
    └── generate_raw_timings.py   # Utility to generate timing arrays
```

## 🙏 Acknowledgments

- [juanboro/esphome-radiolib-cc1101](https://github.com/juanboro/esphome-radiolib-cc1101) — The RadioLib ESPHome component that makes this work
- [RadioLib](https://github.com/jgromes/RadioLib) — Excellent multi-platform radio library
- [ESPHome](https://esphome.io/) — The backbone of our Home Assistant integration
- Broadlink RM4 Pro — Used as reference for protocol timing capture

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
