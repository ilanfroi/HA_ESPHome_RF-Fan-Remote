#!/usr/bin/env python3
"""
Generate ESPHome transmit_raw timing arrays for 433MHz OOK ceiling fan control.

This script takes a 29-bit binary code (or decimal equivalent), calculates the
parity bit, and outputs the raw microsecond timing array ready to paste into an
ESPHome YAML configuration.

Protocol:
  - Bit '1': 1182µs HIGH + 394µs LOW
  - Bit '0': 394µs HIGH + 1182µs LOW
  - Parity 0: trailing 394µs HIGH (short pulse)
  - Parity 1: trailing 1182µs HIGH (long pulse)
  - Frame: no sync, 7093µs inter-frame gap, 10 repetitions

Parity:
  The 30th bit is an even parity bit calculated over bits 1-29.
  Parity = count_of_ones(bits 1-29) mod 2.
  If the number of '1' bits is odd, parity = 1 (LONG pulse).
  If the number of '1' bits is even, parity = 0 (SHORT pulse).

  NOTE: Always verify generated codes against actual Broadlink/SDR captures.
  The empirical timing arrays in the YAML config are the ground truth.

Usage:
  python generate_raw_timings.py --binary "10011001000111011011110010001"
  python generate_raw_timings.py --decimal 320895889
  python generate_raw_timings.py --binary "10011001000111011011110010001" --yaml
  python generate_raw_timings.py --binary "10011001000111011011110010001" --parity 0
"""

import argparse
import sys

# Timing constants (microseconds)
LONG = 1182
SHORT = 394
GAP = 7093
REPETITIONS = 10


def calculate_parity(binary_str: str) -> int:
    """Calculate even parity over a binary string.
    
    Returns the parity bit value:
      0 if number of '1' bits is even
      1 if number of '1' bits is odd
    
    This makes the total count of 1s (data + parity) even.
    """
    ones_count = binary_str.count('1')
    return ones_count % 2


def binary_to_timings(binary_29bit: str, parity_override: int = None) -> list:
    """Convert a 29-bit binary code to ESPHome transmit_raw timing array.
    
    Args:
        binary_29bit: 29-character string of '0' and '1'
        parity_override: If specified, use this parity value instead of calculating
        
    Returns:
        List of integers representing microsecond timings.
        Positive = HIGH, negative = LOW.
    """
    if len(binary_29bit) != 29:
        raise ValueError(f"Expected 29-bit code, got {len(binary_29bit)} bits: {binary_29bit}")
    
    if not all(c in '01' for c in binary_29bit):
        raise ValueError(f"Binary string must contain only '0' and '1': {binary_29bit}")
    
    # Calculate or use override parity
    if parity_override is not None:
        parity = parity_override
    else:
        parity = calculate_parity(binary_29bit)
    
    timings = []
    
    # Encode 29 data bits
    for bit in binary_29bit:
        if bit == '1':
            timings.append(LONG)    # HIGH 1182µs
            timings.append(-SHORT)  # LOW 394µs
        else:
            timings.append(SHORT)   # HIGH 394µs
            timings.append(-LONG)   # LOW 1182µs
    
    # Encode parity bit (trailing pulse only, no LOW after)
    if parity == 1:
        timings.append(LONG)   # LONG trailing pulse
    else:
        timings.append(SHORT)  # SHORT trailing pulse
    
    return timings


def decimal_to_binary(decimal_code: int) -> str:
    """Convert decimal code to 29-bit binary string."""
    if decimal_code < 0 or decimal_code >= 2**29:
        raise ValueError(f"Decimal code must be 0-{2**29 - 1}, got {decimal_code}")
    return format(decimal_code, '029b')


def format_yaml(timings: list, name: str = "Fan Command") -> str:
    """Format timings as ESPHome YAML button configuration."""
    timing_str = ", ".join(str(t) for t in timings)
    
    yaml = f"""  - platform: template
    name: "{name}"
    on_press:
      - remote_transmitter.transmit_raw:
          transmitter_id: rf_tx
          code: [{timing_str}]
          repeat:
            times: {REPETITIONS}
            wait_time: {GAP}us"""
    return yaml


def format_array(timings: list) -> str:
    """Format timings as a simple array string."""
    return "[" + ", ".join(str(t) for t in timings) + "]"


def decode_timings(timings: list) -> tuple:
    """Decode a timing array back to binary code and parity.
    
    Args:
        timings: List of signed integers (positive=HIGH, negative=LOW)
        
    Returns:
        Tuple of (binary_code_29bit, parity_bit)
    """
    bits = ""
    i = 0
    while i < len(timings) - 1:
        high = timings[i]
        low = abs(timings[i + 1])
        
        if abs(high - LONG) < 200 and abs(low - SHORT) < 200:
            bits += "1"
        elif abs(high - SHORT) < 200 and abs(low - LONG) < 200:
            bits += "0"
        else:
            # Might be parity pulse
            break
        i += 2
    
    # Last value is parity pulse
    if i < len(timings):
        last = timings[i] if i == len(timings) - 1 else timings[-1]
        parity = 1 if abs(last - LONG) < 200 else 0
    else:
        parity = None
    
    return bits, parity


# Known code tables for reference/validation
KNOWN_CODES = {
    "hila": {
        "address": "10011001000111011011",
        "commands": {
            "off":     ("10011001000111011011110010001", 0),
            "speed1":  ("10011001000111011011111101000", 0),
            "speed2":  ("10011001000111011011111001000", 0),
            "speed3":  ("10011001000111011011110101001", 1),
            "speed4":  ("10011001000111011011110001001", 1),
            "speed5":  ("10011001000111011011101101010", 0),
            "speed6":  ("10011001000111011011101001010", 0),
            "light":   ("10011001000111011011010110101", 1),
            "reverse": ("10011001000111011011100101011", 1),
            "natural": ("10011001000111011011100001011", 1),
            "timer1h": ("10011001000111011011010010101", 1),
            "timer2h": ("10011001000111011011000110111", 1),
            "timer4h": ("10011001000111011011001110110", 0),
            "timer8h": ("10011001000111011011101010010", 0),
        }
    },
    "bedroom": {
        "address": "01110110110101111010",
        "commands": {
            "off":     ("01110110110101111010110010001", 0),
            "speed1":  ("01110110110101111010111101000", 0),
            "speed2":  ("01110110110101111010111001000", 0),
            "speed3":  ("01110110110101111010110101001", 1),
            "speed4":  ("01110110110101111010110001001", 1),
            "speed5":  ("01110110110101111010101101010", 0),
            "speed6":  ("01110110110101111010101001010", 0),
            "light":   ("01110110110101111010010110101", 1),
            "reverse": ("01110110110101111010100101011", 1),
            "natural": ("01110110110101111010100001011", 1),
            "timer1h": ("01110110110101111010010010101", 1),
            "timer2h": ("01110110110101111010000110111", 1),
            "timer4h": ("01110110110101111010001110110", 0),
            "timer8h": ("01110110110101111010101010010", 0),
        }
    }
}


def list_known_codes():
    """Print all known fan codes."""
    for fan_name, fan_data in KNOWN_CODES.items():
        print(f"\n{'='*60}")
        print(f"Fan: {fan_name.upper()} (address: {fan_data['address']})")
        print(f"{'='*60}")
        print(f"{'Command':<10} {'Binary (29-bit)':<32} {'Decimal':<12} {'Parity'}")
        print(f"{'-'*10} {'-'*31} {'-'*11} {'-'*6}")
        for cmd_name, (code, parity) in fan_data['commands'].items():
            decimal = int(code, 2)
            p_str = f"{parity} ({'LONG' if parity else 'SHORT'})"
            print(f"{cmd_name:<10} {code} {decimal:<12} {p_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate ESPHome transmit_raw timings for 433MHz OOK fan control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --binary "10011001000111011011110010001"
  %(prog)s --decimal 320895889
  %(prog)s --binary "10011001000111011011110010001" --yaml --name "Hila Fan OFF"
  %(prog)s --binary "10011001000111011011110010001" --parity 0
  %(prog)s --list

Fan Code Tables:
  Hila Fan OFF:     320895889  (10011001000111011011110010001) parity=0
  Hila Fan Speed 1: 320895976  (10011001000111011011111101000) parity=0
  Bedroom Fan OFF:  250734481  (01110110110101111010110010001) parity=0
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--binary', '-b', type=str,
                       help='29-bit binary code string (e.g., "10011001000111011011110010001")')
    group.add_argument('--decimal', '-d', type=int,
                       help='Decimal code value (e.g., 320895889)')
    group.add_argument('--list', action='store_true',
                       help='List all known fan codes')
    
    parser.add_argument('--parity', '-p', type=int, choices=[0, 1],
                        help='Override parity bit value (0=SHORT, 1=LONG). '
                             'If not specified, even parity is calculated automatically.')
    parser.add_argument('--yaml', '-y', action='store_true',
                        help='Output as ESPHome YAML button configuration')
    parser.add_argument('--name', '-n', type=str, default="Fan Command",
                        help='Button name for YAML output (default: "Fan Command")')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed breakdown')
    
    args = parser.parse_args()
    
    # Handle --list
    if args.list:
        list_known_codes()
        return
    
    # Get binary code
    if args.binary:
        binary_code = args.binary
    else:
        binary_code = decimal_to_binary(args.decimal)
    
    # Validate
    if len(binary_code) != 29:
        print(f"Error: Expected 29-bit code, got {len(binary_code)} bits", file=sys.stderr)
        sys.exit(1)
    
    # Calculate parity
    if args.parity is not None:
        parity = args.parity
        parity_source = "manual override"
    else:
        parity = calculate_parity(binary_code)
        parity_source = "calculated (even parity)"
    
    # Generate timings
    timings = binary_to_timings(binary_code, parity_override=parity)
    
    # Output
    if args.verbose:
        print(f"{'='*60}")
        print(f"Input code (29 bits): {binary_code}")
        print(f"Decimal value:        {int(binary_code, 2)}")
        print(f"Address (bits 1-20):  {binary_code[:20]}")
        print(f"Command (bits 21-29): {binary_code[20:]}")
        print(f"Ones count:           {binary_code.count('1')}")
        print(f"Parity bit:           {parity} ({'LONG 1182µs' if parity else 'SHORT 394µs'}) [{parity_source}]")
        print(f"Full code (30 bits):  {binary_code}{parity}")
        print(f"Timing array length:  {len(timings)} values")
        print(f"{'='*60}")
        print()
    
    if args.yaml:
        print(format_yaml(timings, args.name))
    else:
        if not args.verbose:
            print(f"Code: {binary_code} (decimal: {int(binary_code, 2)})")
            print(f"Parity: {parity} ({'LONG' if parity else 'SHORT'}) [{parity_source}]")
            print()
        print("ESPHome transmit_raw code:")
        print(f"  code: {format_array(timings)}")
        print(f"  repeat:")
        print(f"    times: {REPETITIONS}")
        print(f"    wait_time: {GAP}us")
    
    # Check against known codes
    for fan_name, fan_data in KNOWN_CODES.items():
        for cmd_name, (known_code, known_parity) in fan_data['commands'].items():
            if known_code == binary_code:
                if parity != known_parity:
                    print(f"\n⚠️  WARNING: Known parity for {fan_name}/{cmd_name} is "
                          f"{known_parity}, but calculated/specified parity is {parity}.")
                    print(f"   Use --parity {known_parity} for the empirically verified value.")
                else:
                    print(f"\n✓ Matches known code: {fan_name}/{cmd_name}")
                break


if __name__ == "__main__":
    main()
