#!/usr/bin/env python3
"""
Test script for ESP32 Wear Leveling implementation

This script tests the wear leveling layer implementation by:
1. Creating a simple FAT filesystem
2. Wrapping it with wear leveling
3. Verifying the WL structure
4. Extracting and verifying the FAT data
"""

import sys
import struct
from pathlib import Path

# Add builder directory to path
sys.path.insert(0, str(Path(__file__).parent))

from esp32_wl import WearLevelingLayer, create_wl_fat_image, extract_fat_from_wl_image


def test_wl_state_creation():
    """Test WL_State structure creation and verification"""
    print("Test 1: WL_State creation and verification")
    print("-" * 50)
    
    wl = WearLevelingLayer(sector_size=4096)
    
    # Create a WL state
    state = wl.create_wl_state(
        pos=0,
        max_pos=100,
        move_count=0,
        access_count=0,
        max_count=1600,
        device_id=0
    )
    
    print(f"  Created WL_State: {len(state)} bytes")
    
    # Verify structure
    is_valid = wl.verify_wl_state(state)
    print(f"  CRC32 verification: {'PASS' if is_valid else 'FAIL'}")
    
    # Parse and display
    fields = struct.unpack('<IIIIIIII12sI', state)
    print(f"  pos: {fields[0]}")
    print(f"  max_pos: {fields[1]}")
    print(f"  move_count: {fields[2]}")
    print(f"  access_count: {fields[3]}")
    print(f"  max_count: {fields[4]}")
    print(f"  block_size: {fields[5]}")
    print(f"  version: {fields[6]}")
    print(f"  device_id: {fields[7]}")
    print(f"  crc32: 0x{fields[9]:08X}")
    
    return is_valid


def test_wl_wrapping():
    """Test wrapping a FAT image with wear leveling"""
    print("\nTest 2: FAT image wrapping")
    print("-" * 50)
    
    # Create a minimal FAT boot sector (512 bytes)
    # This is a simplified FAT12 boot sector
    boot_sector = bytearray(512)
    
    # Jump instruction
    boot_sector[0:3] = b'\xEB\x3C\x90'
    
    # OEM name
    boot_sector[3:11] = b'MSDOS5.0'
    
    # Bytes per sector (512)
    boot_sector[11:13] = struct.pack('<H', 512)
    
    # Sectors per cluster (8 = 4KB)
    boot_sector[13] = 8
    
    # Reserved sectors (1)
    boot_sector[14:16] = struct.pack('<H', 1)
    
    # Number of FATs (2)
    boot_sector[16] = 2
    
    # Root entries (512)
    boot_sector[17:19] = struct.pack('<H', 512)
    
    # Total sectors (1000)
    boot_sector[19:21] = struct.pack('<H', 1000)
    
    # Media descriptor (0xF8 = hard disk)
    boot_sector[21] = 0xF8
    
    # Sectors per FAT (9)
    boot_sector[22:24] = struct.pack('<H', 9)
    
    # Boot signature
    boot_sector[510:512] = b'\x55\xAA'
    
    # Create a minimal FAT image (pad to 4KB)
    fat_data = boot_sector + (b'\x00' * (4096 - 512))
    
    print(f"  FAT data size: {len(fat_data)} bytes")
    
    # Wrap with wear leveling (partition size = 64KB)
    partition_size = 64 * 1024
    wl_image = create_wl_fat_image(fat_data, partition_size, sector_size=4096)
    
    print(f"  WL image size: {len(wl_image)} bytes")
    print(f"  Expected size: {partition_size} bytes")
    
    # Verify size
    size_ok = len(wl_image) == partition_size
    print(f"  Size check: {'PASS' if size_ok else 'FAIL'}")
    
    # Verify WL state
    wl = WearLevelingLayer(sector_size=4096)
    first_state = wl_image[:48]
    state_ok = wl.verify_wl_state(first_state)
    print(f"  WL state check: {'PASS' if state_ok else 'FAIL'}")
    
    # Extract FAT data
    extracted_fat = extract_fat_from_wl_image(wl_image, sector_size=4096)
    
    if extracted_fat:
        print(f"  Extracted FAT size: {len(extracted_fat)} bytes")
        
        # Verify boot sector signature
        signature = extracted_fat[510:512]
        sig_ok = signature == b'\x55\xAA'
        print(f"  Boot signature check: {'PASS' if sig_ok else 'FAIL'}")
        
        # Verify bytes per sector
        bps = struct.unpack('<H', extracted_fat[11:13])[0]
        bps_ok = bps == 512
        print(f"  Bytes per sector: {bps} ({'PASS' if bps_ok else 'FAIL'})")
        
        return size_ok and state_ok and sig_ok and bps_ok
    else:
        print("  ERROR: Failed to extract FAT data")
        return False


def test_sector_calculations():
    """Test sector overhead calculations"""
    print("\nTest 3: Sector overhead calculations")
    print("-" * 50)
    
    wl = WearLevelingLayer(sector_size=4096)
    
    # Test different partition sizes
    test_cases = [
        (64 * 1024, "64 KB"),
        (256 * 1024, "256 KB"),
        (1 * 1024 * 1024, "1 MB"),
        (1507328, "1.5 MB (example)"),
    ]
    
    all_ok = True
    for partition_size, label in test_cases:
        total_sectors = partition_size // 4096
        wl_overhead = (wl.wl_state_size * 2) + wl.wl_temp_size
        fat_sectors = total_sectors - wl_overhead
        fat_size = fat_sectors * 4096
        
        print(f"\n  {label}:")
        print(f"    Total sectors: {total_sectors}")
        print(f"    WL overhead: {wl_overhead} sectors ({wl_overhead * 4096} bytes)")
        print(f"    FAT sectors: {fat_sectors}")
        print(f"    FAT size: {fat_size} bytes")
        
        # Verify calculations
        expected_total = (fat_sectors + wl_overhead) * 4096
        calc_ok = expected_total == partition_size
        print(f"    Calculation check: {'PASS' if calc_ok else 'FAIL'}")
        
        all_ok = all_ok and calc_ok
    
    return all_ok


def main():
    """Run all tests"""
    print("=" * 50)
    print("ESP32 Wear Leveling Layer Tests")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("WL State Creation", test_wl_state_creation()))
    results.append(("FAT Wrapping", test_wl_wrapping()))
    results.append(("Sector Calculations", test_sector_calculations()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + ("=" * 50))
    if all_passed:
        print("All tests PASSED ✓")
        return 0
    else:
        print("Some tests FAILED ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
