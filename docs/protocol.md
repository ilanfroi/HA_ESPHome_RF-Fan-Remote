# Protocol Documentation: 433MHz OOK Ceiling Fan Control

## Overview

This document describes the reverse-engineered RF protocol used by certain 433MHz ceiling fans (commonly sold under various brand names in Israel and other markets). The protocol uses On-Off Keying (OOK) modulation at 433.92 MHz with a fixed-length 30-bit frame.

## Reverse Engineering Story

### Discovery Process

1. **Initial Capture**: Used a Broadlink RM4 Pro to learn the remote's RF codes via its app
2. **Base64 Decode**: Extracted the raw timing data from Broadlink's base64-encoded format
3. **Pattern Recognition**: Identified consistent 1182µs / 394µs timing pairs (3:1 ratio)
4. **Bit Mapping**: Mapped timing patterns to binary (LONG-SHORT = 1, SHORT-LONG = 0)
5. **Code Comparison**: Compared all button codes to identify address vs. command bits
6. **Parity Discovery**: Found the mysterious 30th bit through cross-device comparison

### The Parity Bit Discovery

The hardest part was identifying the 30th bit. Initial analysis suggested 29-bit codes, but:

1. Decoded Broadlink base64 for the same button across two different fans
2. Noticed the decoded timings had one extra pulse after the 29th bit
3. The extra pulse was SHORT (394µs) for some codes and LONG (1182µs) for others
4. Counted '1' bits in all 29-bit codes — codes with even number of 1s had SHORT trailing pulse
5. **Conclusion**: Bit 30 is an **even parity bit** over bits 1-29

The parity bit encoding is unique: it's a trailing pulse with NO subsequent LOW period (the inter-frame gap serves as the "LOW").

## Protocol Specification

### Physical Layer

| Parameter | Value |
|-----------|-------|
| Frequency | 433.92 MHz |
| Modulation | OOK (On-Off Keying) |
| Data Rate | ~634 bps (1576µs per bit) |

### Bit Encoding

The protocol uses a Manchester-like encoding with a 3:1 timing ratio:

```
Bit '1':  ████████████░░░░     (1182µs HIGH, 394µs LOW)
Bit '0':  ████░░░░░░░░░░░░     (394µs HIGH, 1182µs LOW)
```

Each bit period is exactly 1576µs (1182 + 394).

### Parity Bit Encoding (Bit 30)

The parity bit is special — it's only a HIGH pulse with no explicit LOW:

```
Parity 0: ████                 (394µs HIGH, then inter-frame gap)
Parity 1: ████████████         (1182µs HIGH, then inter-frame gap)
```

The inter-frame gap (7093µs silence) follows immediately.

### Frame Structure

```
┌──────────────────────────────────────────────────────────┐
│ Bit1 Bit2 ... Bit29 │ Parity │ ──── 7093µs gap ──── │ (repeat)
└──────────────────────────────────────────────────────────┘

Total frame time: 29 × 1576µs + parity_pulse + 7093µs ≈ 53ms
Transmission: 10 repetitions ≈ 530ms total
```

### Code Format

```
Bits 1-20:  Fan Address (unique per fan/remote pair)
Bits 21-29: Command Code (identifies the button pressed)
Bit 30:     Even Parity (over bits 1-29)
```

## Complete Code Tables

### Hila Fan (Address: `10011001000111011011`)

| Command | Binary (29 bits) | Decimal | Parity | Full 30-bit |
|---------|-------------------|---------|--------|-------------|
| OFF | `10011001000111011011110010001` | 320895889 | 0 | `10011001000111011011110010001`+S |
| Speed 1 | `10011001000111011011111101000` | 320895976 | 0 | `10011001000111011011111101000`+S |
| Speed 2 | `10011001000111011011111001000` | 320895944 | 0 | `10011001000111011011111001000`+S |
| Speed 3 | `10011001000111011011110101001` | 320895913 | 1 | `10011001000111011011110101001`+L |
| Speed 4 | `10011001000111011011110001001` | 320895881 | 1 | `10011001000111011011110001001`+L |
| Speed 5 | `10011001000111011011101101010` | 320895850 | 0 | `10011001000111011011101101010`+S |
| Speed 6 | `10011001000111011011101001010` | 320895818 | 0 | `10011001000111011011101001010`+S |
| Light | `10011001000111011011010110101` | 320895669 | 1 | `10011001000111011011010110101`+L |
| Reverse | `10011001000111011011100101011` | 320895787 | 1 | `10011001000111011011100101011`+L |
| Natural | `10011001000111011011100001011` | 320895755 | 1 | `10011001000111011011100001011`+L |
| Timer 1H | `10011001000111011011010010101` | 320895637 | 1 | `10011001000111011011010010101`+L |
| Timer 2H | `10011001000111011011000110111` | 320895543 | 1 | `10011001000111011011000110111`+L |
| Timer 4H | `10011001000111011011001110110` | 320895606 | 0 | `10011001000111011011001110110`+S |
| Timer 8H | `10011001000111011011101010010` | 320895826 | 0 | `10011001000111011011101010010`+S |

> **S** = SHORT parity pulse (394µs), **L** = LONG parity pulse (1182µs)

### Bedroom Fan (Address: `01110110110101111010`)

| Command | Binary (29 bits) | Decimal | Parity | Full 30-bit |
|---------|-------------------|---------|--------|-------------|
| OFF | `01110110110101111010110010001` | 250734481 | 0 | `01110110110101111010110010001`+S |
| Speed 1 | `01110110110101111010111101000` | 250734568 | 0 | `01110110110101111010111101000`+S |
| Speed 2 | `01110110110101111010111001000` | 250734536 | 0 | `01110110110101111010111001000`+S |
| Speed 3 | `01110110110101111010110101001` | 250734505 | 1 | `01110110110101111010110101001`+L |
| Speed 4 | `01110110110101111010110001001` | 250734473 | 1 | `01110110110101111010110001001`+L |
| Speed 5 | `01110110110101111010101101010` | 250734442 | 0 | `01110110110101111010101101010`+S |
| Speed 6 | `01110110110101111010101001010` | 250734410 | 0 | `01110110110101111010101001010`+S |
| Light | `01110110110101111010010110101` | 250734261 | 1 | `01110110110101111010010110101`+L |
| Reverse | `01110110110101111010100101011` | 250734379 | 1 | `01110110110101111010100101011`+L |
| Natural | `01110110110101111010100001011` | 250734347 | 1 | `01110110110101111010100001011`+L |
| Timer 1H | `01110110110101111010010010101` | 250734229 | 1 | `01110110110101111010010010101`+L |
| Timer 2H | `01110110110101111010000110111` | 250734135 | 1 | `01110110110101111010000110111`+L |
| Timer 4H | `01110110110101111010001110110` | 250734198 | 0 | `01110110110101111010001110110`+S |
| Timer 8H | `01110110110101111010101010010` | 250734418 | 0 | `01110110110101111010101010010`+S |

## Command Pattern Analysis

Looking at just the command portion (bits 21-29):

| Command | Bits 21-29 | Notes |
|---------|-----------|-------|
| OFF | `110010001` | |
| Speed 1 | `111101000` | |
| Speed 2 | `111001000` | |
| Speed 3 | `110101001` | |
| Speed 4 | `110001001` | |
| Speed 5 | `101101010` | |
| Speed 6 | `101001010` | |
| Light | `010110101` | |
| Reverse | `100101011` | |
| Natural | `100001011` | |
| Timer 1H | `010010101` | |
| Timer 2H | `000110111` | |
| Timer 4H | `001110110` | |
| Timer 8H | `101010010` | |

**Observation**: The command codes are identical across all fans — only the 20-bit address prefix differs.

## Decoding Broadlink RF Codes

If you have a Broadlink RM4 Pro, you can extract raw timings from its learned codes:

### Step 1: Learn the Code

Use the Broadlink app or `python-broadlink` library to learn an RF code from your remote.

### Step 2: Extract Base64

The learned code is stored as a base64-encoded byte array.

### Step 3: Decode

```python
import base64

# Example Broadlink learned RF code (base64)
code_b64 = "your_base64_code_here"
code_bytes = base64.b64decode(code_b64)

# Broadlink RF format:
# Byte 0: length
# Byte 1: repeat count
# Bytes 4+: timing pairs (big-endian uint16, units of ~32.84µs)
# 
# Parse timing values:
offset = 4
timings = []
while offset < len(code_bytes) - 1:
    if code_bytes[offset] == 0:
        # Extended format: next 2 bytes are the value
        value = (code_bytes[offset+1] << 8) | code_bytes[offset+2]
        offset += 3
    else:
        value = code_bytes[offset]
        offset += 1
    timings.append(value * 32.84)  # Convert to microseconds

print("Raw timings (µs):", timings)
```

### Step 4: Map to Binary

```python
LONG = 1182  # ±tolerance
SHORT = 394

bits = ""
i = 0
while i < len(timings) - 1:
    high = timings[i]
    low = timings[i + 1]
    
    if abs(high - LONG) < 200 and abs(low - SHORT) < 200:
        bits += "1"
    elif abs(high - SHORT) < 200 and abs(low - LONG) < 200:
        bits += "0"
    else:
        print(f"Unknown pattern at index {i}: {high}/{low}")
    i += 2

# Last pulse (parity):
last = timings[-1]
parity = "1" if abs(last - LONG) < 200 else "0"

print(f"Data bits: {bits}")
print(f"Parity: {parity}")
```

## Timing Precision

The timing values used in this project come from Broadlink RM4 Pro captures averaged across multiple samples:

| Symbol | Nominal (µs) | Acceptable Range |
|--------|-------------|------------------|
| LONG   | 1182        | 982 - 1382       |
| SHORT  | 394         | 194 - 594        |
| GAP    | 7093        | 6000 - 8000      |

The fan's receiver has significant timing tolerance (tested up to ±30% and still works).

## Comparison with Standard Protocols

This protocol is similar to but NOT compatible with:

- **RC Switch Protocol 1**: Similar 3:1 ratio but different absolute timings and has sync pulse
- **EV1527**: Uses sync pulse, different frame structure
- **PT2262**: Different bit period, has sync

The key differences:
1. **No sync pulse** — the protocol relies on the inter-frame gap for synchronization
2. **Even parity bit** — most cheap RF protocols don't include error checking
3. **Trailing pulse encoding** for parity — unique to this protocol

## Security Note

This is a **fixed code** protocol with no rolling codes or encryption. Any captured transmission can be replayed indefinitely. This is typical for ceiling fan remotes where security is not a concern.
