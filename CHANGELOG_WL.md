# Changelog: ESP32 Wear Leveling Support for FAT Filesystem

## Summary

Added ESP32 Wear Leveling layer support to FAT filesystem image creation. This fixes the issue where FAT images created with `fatfs-python` were not recognized by the ESP32 Arduino Core's `FFat` library.

## Problem

The ESP32 Arduino Core's `FFat.begin()` function uses `esp_vfs_fat_spiflash_mount_rw_wl()`, which expects FAT partitions to be wrapped with a wear leveling layer. Images created with raw `fatfs-python` lacked this layer, causing mount failures.

## Solution

Implemented a Python module (`esp32_wl.py`) that wraps FAT filesystem images with the ESP-IDF wear leveling structure.

## Changes

### New Files

1. **`builder/esp32_wl.py`**
   - Implements `WearLevelingLayer` class
   - Creates WL_State structures with proper CRC32
   - Wraps FAT images with wear leveling metadata
   - Extracts FAT data from wear-leveling wrapped images

2. **`builder/test_wl.py`**
   - Unit tests for wear leveling implementation
   - Verifies WL_State creation and CRC32
   - Tests FAT image wrapping and extraction
   - Validates sector overhead calculations

3. **`WEAR_LEVELING.md`**
   - Comprehensive documentation of wear leveling structure
   - WL_State format specification
   - Configuration and usage examples
   - Troubleshooting guide

4. **`CHANGELOG_WL.md`**
   - This file

### Modified Files

1. **`builder/main.py`**
   - Modified `build_fatfs_image()` to wrap FAT images with wear leveling
   - Modified `download_fatfs()` to detect and extract wear-leveling wrapped images
   - Added wear leveling overhead calculations
   - Added informative output messages

2. **`FATFS_INTEGRATION.md`**
   - Updated technical details section
   - Added wear leveling layer explanation
   - Updated build and download process descriptions

## Technical Details

### Wear Leveling Structure

```
Offset    | Size      | Description
----------|-----------|----------------------------------
0x0000    | 4096      | WL State Copy 1
0x1000    | 4096      | WL State Copy 2
0x2000    | N×4096    | FAT Filesystem Data
N×4096    | 4096      | Temp Sector (for WL operations)
(N+1)×4096| 4096      | WL State Copy 3
(N+2)×4096| 4096      | WL State Copy 4
```

### WL_State Structure (48 bytes)

```c
struct WL_State {
    uint32_t pos;           // 0x00: Current position
    uint32_t max_pos;       // 0x04: Maximum position
    uint32_t move_count;    // 0x08: Move counter
    uint32_t access_count;  // 0x0C: Access counter
    uint32_t max_count;     // 0x10: Maximum count
    uint32_t block_size;    // 0x14: Block size (4096)
    uint32_t version;       // 0x18: WL version (2)
    uint32_t device_id;     // 0x1C: Device ID
    uint8_t  reserved[12];  // 0x20: Reserved (0xFF)
    uint32_t crc32;         // 0x2C: CRC32 checksum
};
```

### Overhead Calculation

For a 1.5 MB partition (1,507,328 bytes):
- Total sectors: 368 (1,507,328 / 4096)
- WL overhead: 5 sectors (20,480 bytes)
  - 2 state sectors at start
  - 1 temp sector
  - 2 state sectors at end
- FAT data: 363 sectors (1,486,848 bytes)

## Testing

All tests pass successfully:

```bash
$ python3 builder/test_wl.py
==================================================
ESP32 Wear Leveling Layer Tests
==================================================
Test 1: WL_State creation and verification
--------------------------------------------------
  Created WL_State: 48 bytes
  CRC32 verification: PASS

Test 2: FAT image wrapping
--------------------------------------------------
  FAT data size: 4096 bytes
  WL image size: 65536 bytes
  Size check: PASS
  WL state check: PASS
  Boot signature check: PASS
  Bytes per sector: 512 (PASS)

Test 3: Sector overhead calculations
--------------------------------------------------
  [All partition sizes: PASS]

==================================================
All tests PASSED ✓
==================================================
```

## Usage Example

### Building FAT Image

```bash
$ pio run -t buildfs

Building FS image from 'data' directory to .pio/build/esp32dev/fatfs.bin
Wrapping FAT image with ESP32 Wear Leveling layer...
  Partition size: 1507328 bytes (368 sectors)
  FAT data size: 1486848 bytes (363 sectors)
  WL overhead: 5 sectors
Successfully created wear-leveling FAT image
```

### Downloading from Device

```bash
$ pio run -t download_fatfs

Downloading partition table from /dev/ttyUSB0...
Found filesystem partition (subtype 0x81):
  Start: 0x290000
  Size: 0x170000 (1507328 bytes)

Downloading filesystem from device...
Downloaded to .pio/build/esp32dev/downloaded_fs_0x290000_0x170000.bin

Detected Wear Leveling layer, extracting FAT data...
  Extracted FAT data: 1486848 bytes

Extracting files:
  FILE: /test.txt (12 bytes)
  FILE: /README.md (1234 bytes)

Successfully extracted 2 file(s) to unpacked_fs
```

## Compatibility

- **ESP-IDF**: v4.x, v5.x
- **Arduino-ESP32**: 2.x, 3.x
- **Sector Size**: 4096 bytes (standard)
- **FAT Types**: FAT12, FAT16, FAT32

## Migration Guide

### For Existing Projects

If you have an existing project that was using raw FAT images:

1. **Update platform-espressif32**:
   ```bash
   git pull
   ```

2. **Rebuild filesystem**:
   ```bash
   pio run -t buildfs
   ```

3. **Upload to device**:
   ```bash
   pio run -t uploadfs
   ```

4. **Verify**:
   ```bash
   pio run -t monitor
   ```
   
   You should see: `FFat mounted successfully`

### No Code Changes Required

The Arduino sketch code remains unchanged. The wear leveling layer is transparent to the application.

## Future Enhancements

Potential improvements:
1. Support for different sector sizes (512, 1024, 2048)
2. Configurable update rate
3. Wear leveling statistics reporting
4. Integration with ESP-IDF's wear leveling tools

## References

- [ESP-IDF Wear Levelling Component](https://github.com/espressif/esp-idf/tree/master/components/wear_levelling)
- [ESP-IDF FAT Filesystem](https://github.com/espressif/esp-idf/tree/master/components/fatfs)
- [Arduino-ESP32 FFat Library](https://github.com/espressif/arduino-esp32/tree/master/libraries/FFat)
- [mk_esp32fat Tool](https://github.com/TobleMiner/mk_esp32fat)

## Credits

- **ESP-IDF Team**: Original wear leveling implementation
- **fatfs-python**: Base FAT filesystem library
- **fatfs-ng**: Enhanced Python wrapper with directory traversal

## License

Apache License 2.0 (same as platform-espressif32)
