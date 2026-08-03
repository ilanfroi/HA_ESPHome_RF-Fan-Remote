# ESP32 CC1101 Ceiling Fan RF Control (ESPHome)

> Full TX+RX control of 433MHz OOK ceiling fans using ESP32-C3 + CC1101 (Ebyte E07-M1101D) via ESPHome and Home Assistant.

## ✨ Key Features
- **Bidirectional Control** — TX commands to the fan + RX state tracking from the physical remote
- **Half-Duplex on Single Pin** — RadioLib handles TX/RX mode switching on GDO0
- **3 Fan Support** — Bedroom (6-speed), Hila (6-speed), Tal (5-speed + LED brightness)
- **Complete Protocol Reverse-Engineering** — 30-bit OOK format with parity bit (EVEN and ODD variants)
- **TX Loopback Protection** — Cooldown prevents self-received frames from bouncing toggle states
- **Sync Buttons** — Zero ESP state without sending RF to re-sync with physical fan
- **Power Switch Gating** — RF processing blocked when smart switch is OFF; first RF signal wakes the switch
- **Home Assistant Integration** — Full fan entities with speed, light, direction, natural/oscillate modes
- **No Hub Required** — Direct RF communication, no Broadlink or proprietary bridge needed

---

## 📡 Protocol Overview

The ceiling fans use a 30-bit OOK (On-Off Keying) protocol at 433.92 MHz:

```
┌─────────────────────────────┬───────────┬────────┐
│   29 Data Bits              │ Parity(1) │  Gap   │
│ [Address 20b][Command 9b]   │ Even/Odd  │ 7093µs │
└─────────────────────────────┴───────────┴────────┘
```

### Bit Encoding

| Bit Value | HIGH Duration | LOW Duration | Total |
|----------:|--------------|-------------|--------|
| 1         | 1182 µs      | 394 µs      | 1576 µs |
| 0         | 394 µs       | 1182 µs     | 1576 µs |

### Parity Bit (Bit 30)

The parity bit uses a trailing pulse encoding (no LOW period follows):
- Parity 0 → SHORT pulse (394 µs HIGH)
- Parity 1 → LONG pulse (1182 µs HIGH)

**CRITICAL**: Two parity modes exist:

| Fan | Parity Mode | Rule |
|-----|------------|------|
| Bedroom | EVEN | Even 1-count → SHORT trailing, Odd → LONG |
| Hila | EVEN | Same as Bedroom |
| Tal | **ODD** | Even 1-count → LONG trailing, Odd → SHORT (inverted!) |

The ODD parity discovery was the breakthrough that made Tal TX work — all previous attempts used EVEN parity, inverting every code.

### Frame Structure
- No sync/preamble pulse
- 30 bits per frame (29 data + 1 parity)
- 7093 µs inter-frame gap (silence)
- 10 repetitions per transmission (Bedroom/Hila), 6 for Tal

> 📖 See [docs/protocol.md](docs/protocol.md) for the complete reverse-engineering documentation and code tables.

---

## 🔧 Hardware

### Components

| Component | Description |
|-----------|-------------|
| ESP32-C3 Super Mini Plus | Microcontroller with WiFi |
| Ebyte E07-M1101D | CC1101 433MHz RF module (SPI) |

### Wiring

| CC1101 Pin | ESP32-C3 Pin | Function |
|-----------|-------------|---------|
| GDO0 | GPIO2 | TX Data / RX Data (half-duplex) |
| CSN | GPIO7 | SPI Chip Select |
| SCK | GPIO4 | SPI Clock |
| MOSI | GPIO6 | SPI Data In |
| MISO | GPIO5 | SPI Data Out |
| VCC | 3.3V | Power |
| GND | GND | Ground |

> ⚠️ The E07-M1101D operates at 3.3V. Do NOT connect to 5V.

---

## 🏗️ Architecture

```
Physical Remote ──── 433MHz ────► CC1101/ESP32 (RX) ──► HA state update
                                         │
HA UI / Automation ──► CC1101/ESP32 (TX) ── 433MHz ──► Ceiling Fan
                                         │
                              (RX picks up own TX = loopback, blocked by cooldown)
```

### HA Integration Stack
```
ESPHome buttons (TX) ◄── HA template fan / script.fan_set_speed_rf2
ESPHome sensors (RX) ──► HA template fan state / template lights
Power switches ──────── gate RX processing + save/restore state on toggle
```

### RadioLib Half-Duplex Architecture

This project uses the [esphome-radiolib-cc1101](https://github.com/juanboro/esphome-radiolib-cc1101) external component, which leverages RadioLib for proper CC1101 control.

The CC1101 module handles the 433.92 MHz carrier generation internally. The ESP32 GPIO (GDO0) simply toggles HIGH/LOW for OOK modulation — no PWM carrier needed from the MCU.

**Pin Mode Switching:**
- TX Mode: output + input + pullup + open_drain (allows RadioLib to drive the pin)
- RX Mode: input + pullup (listens for incoming signals)

**State Machine:**
```
on_boot → recv()
on_transmit → xmit()
on_complete → recv()
OTA on_begin → standby()
```

---

## 🛡️ TX Loopback Protection

When the CC1101 transmits (10 repetitions), it also receives its own signal as 9+ RX frames. For toggle commands (light, natural, reverse), this would bounce the state back and forth.

**Solution:** TX button sets `cooldown = true` BEFORE the `remote_transmitter.transmit_raw` action, then executes a reset script (1500ms delay). The RX handler checks the cooldown flag and skips if set.

```
TX button pressed → set cooldown → toggle state → send RF (10 reps)
                                                       │
RX receives loopback (9 frames) → check cooldown → BLOCKED ✓
                                                       │
After 1500ms → cooldown resets → RX from physical remote works again
```

---

## 🔄 Sync Buttons

Each fan has a **Sync** button that zeroes all state globals and publishes without sending any RF.

**Usage:** When ESP state drifts from the physical fan (e.g., ESP was offline during remote use):
1. Use the physical remote to turn the fan completely OFF (speed 0, light off)
2. Press the Sync button in HA → ESP zeros all state to match
3. ✅ Synced — future commands track correctly

| Fan | Entity ID |
|-----|-----------|
| Bedroom | `button.bedrooms_rf2_bedroom_fan_sync` |
| Hila | `button.bedrooms_rf2_hila_fan_sync` |
| Tal | `button.bedrooms_rf2_tal_fan_sync` |

---

## ⚡ Power Switch Gating

When the smart power switch is OFF:
- All RX processing is blocked (state frozen)
- State is saved to globals

When the power switch turns ON:
- If state is zeroed → normal restore from saved state
- If state is already set (by RF) → skip restore (RF woke the switch)

**RF-Wakes-Switch:** If the physical remote is used while the power switch is OFF, the RX handler:
1. Processes the command (updates state)
2. Calls `homeassistant.service: switch.turn_on` on the power switch
3. Power-ON handler detects non-zero state and skips restore

---

## 🚨 Critical: ESPHome CC1101 TX Bug

ESPHome's built-in `spi:` + `cc1101:` TX is **BROKEN** ([Issue #16876](https://github.com/esphome/issues/issues/16876)).

The bug: `pin_mode()` called during TX setup severs the RMT peripheral's connection to the GPIO pad. The CC1101 configures correctly via SPI, but no signal appears on GDO0.

**Solution:** Use RadioLib's external component which manages pin modes correctly.

---

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

---

## 🚀 Quick Start

1. Clone this repo
2. Copy `esphome/bedrooms-rf2.yaml` to your ESPHome config directory
3. Update the WiFi credentials and API key placeholders
4. Flash to your ESP32-C3
5. Add the device in Home Assistant
6. Configure HA template fans and template lights (see below)

### HA Configuration Required

**Template Fans** (`templates/fans.yaml`):
- Bedroom Fan: speed_count=6, uses `script.fan_set_speed_rf2`
- Hila Fan: speed_count=6, uses `script.fan_set_speed_rf2`
- Tal Fan: speed_count=5, uses `script.fan_set_speed_rf2`

**Template Lights** (`templates/fan_light.yaml`):
- Bedroom/Hila: toggle via `button.press` on TX light button
- Tal: explicit modes (off/normal/warm/cold) + LED brightness (0-8 levels)

**Key Scripts:**
- `script.fan_set_speed_rf2` — Set fan to specific speed (mode: restart)
- `script.fan_speed_step_rf2` — Increment/decrement speed by 1 step
- `script.tal_fan_set_brightness_rf2` — Loop LED+/LED- presses to reach target

**Entity Naming:**
- TX buttons: `button.bedrooms_rf2_{fan}_tx_{command}`
- RX sensors: `sensor.bedrooms_rf2_{fan}_speed`, `binary_sensor.bedrooms_rf2_{fan}_light`
- Speed step script `fan` param: use sensor suffix (`tal_fan`, `bedroom_fan`, `hila_fan`)

---

## 📝 Adding Your Own Fan Codes

### Step 1: Capture Codes from Your Remote
Use the RX configuration to capture raw codes from your physical remote. Check ESPHome logs for received `rc_switch_raw` codes.

### Step 2: Identify the Pattern
- First ~20 bits = fan address (same for all buttons on one remote)
- Last ~9 bits = command (changes per button)
- Bit 30 = parity of bits 1-29 (check if EVEN or ODD for your fan!)

### Step 3: Calculate Parity & Generate Timings
Use the included Python utility:
```bash
# From binary code (29 bits) — EVEN parity (default)
python tools/generate_raw_timings.py --binary "10011001000111011011110010001"

# ODD parity (for fans that use inverted parity)
python tools/generate_raw_timings.py --binary "10011001000111011011110010001" --odd

# From decimal code
python tools/generate_raw_timings.py --decimal 320895889
```

### Step 4: Add to ESPHome Config
Copy the generated `transmit_raw` timing array into your YAML button.

---

## 💡 Lessons Learned

1. **ODD vs EVEN Parity** — Not all fans use the same parity! Bedroom/Hila use EVEN; Tal uses ODD. Discovered by decoding Broadlink base64 captures. This was the #1 blocker for Tal TX.

2. **TX Loopback is Real** — CC1101 receives its own transmissions. For toggle commands, this bounces the state. Cooldown flags before TX are essential.

3. **ESPHome's Built-in CC1101 TX is Broken** — Hours debugging SPI before finding the GPIO/RMT conflict. Use RadioLib external component.

4. **Defective Modules vs Protocol Issues** — Don't blame hardware. If TX reaches other receivers but the target doesn't respond, check protocol encoding (especially parity).

5. **rc_switch TX Doesn't Work (But RX Does)** — `rc_switch_raw` with protocol 1 receives fine at 50% tolerance, but transmitting via rc_switch produces incorrect timing. Always use `transmit_raw`.

6. **Buttons, Not Switches** — TX entities should be ESPHome `button:` (fires once) not `switch:` (has toggle state). Prevents accidental double-toggles.

7. **Broadlink Base64 Decoding** — The key to unlocking new fan codes. Decode the base64, parse pulse pairs, map to binary, determine parity mode.

8. **Entity Naming Matters** — Scripts that build sensor names from parameters need exact suffixes. `sensor.bedrooms_rf2_tal_fan_speed` needs `fan: tal_fan`, not `fan: tal`.

---

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

---

## 🙏 Acknowledgments
- [juanboro/esphome-radiolib-cc1101](https://github.com/juanboro/esphome-radiolib-cc1101) — The RadioLib ESPHome component that makes this work
- [RadioLib](https://github.com/jgromes/RadioLib) — Excellent multi-platform radio library
- [ESPHome](https://esphome.io) — The backbone of our Home Assistant integration
- Broadlink RM4 Pro — Used as reference for protocol timing capture and code extraction

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
