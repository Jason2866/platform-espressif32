# FatFS Integration - Change Overview

## Summary

FatFS has been integrated as a Python module in platform-espressif32, analogous to LittleFS. The integration enables building, uploading, and downloading FatFS filesystem images.

## Modified Files

### 1. `builder/penv_setup.py`

**Change**: Added Python dependency

```python
python_deps = {
    ...
    "littlefs-python": ">=0.16.0",
    "fatfs": ">=0.1.2",  # NEW
    ...
}
```

### 2. `builder/main.py`

**Changes**:

#### a) Added import (line ~25)

```python
from littlefs import LittleFS
from fatfs import Partition, RamDisk  # NEW
```

#### b) New function: `build_fatfs_image()` (after `build_fs_image()`)

Creates FatFS images from a directory:
- Uses RamDisk as backend
- Formats the filesystem
- Copies all files from source directory
- Writes the image as .bin file

```python
def build_fatfs_image(target, source, env):
    """Build FatFS filesystem image using fatfs-python."""
    # ... Implementation
```

#### c) New function: `download_fatfs()` (after `download_littlefs()`)

Downloads FatFS images from device:
- Reads partition table
- Identifies FAT partition (Subtype 0x81)
- Downloads filesystem image
- Extracts files (limited functionality)

```python
def download_fatfs(target, source, env):
    """Download FAT filesystem from device and extract to directory."""
    # ... Implementation
```

#### d) Extended DataToBin Builder (line ~650)

```python
DataToBin=Builder(
    action=env.VerboseAction(
        build_fs_image if filesystem == "littlefs" else (
            build_fatfs_image if filesystem == "fatfs" else " ".join(...)  # NEW
        ),
        ...
    ),
    ...
)
```

#### e) Extended switch_off_ldf() (line ~535)

```python
fs_targets = {"uploadfs", "uploadfsota", "buildfs", "erase", 
              "download_littlefs", "download_fatfs"}  # download_fatfs NEW
```

#### f) Added Platform Target (line ~1520)

```python
env.AddPlatformTarget(
    "download_fatfs",
    None,
    download_fatfs,
    "Download and extract FatFS filesystem from device",
)
```

### 3. `platform.py`

**Change**: Removed tool-mkfatfs installation

```python
def _install_filesystem_tool(self, filesystem: str) -> None:
    """Install filesystem-specific tools based on the filesystem type."""
    # LittleFS and FatFS are handled by Python modules
    # Only install tools for other filesystems
    if filesystem == "spiffs":
        self.install_tool("tool-mkspiffs")
```

### 4. `platform.json`

**Change**: Removed tool-mkfatfs package definition

The `tool-mkfatfs` package entry has been removed since FatFS is now handled by the `fatfs-python` module.

## New Files

### 1. `FATFS_INTEGRATION.md`

Complete documentation of the FatFS integration:
- Feature overview
- Configuration examples
- Usage guide
- Technical details
- Comparison LittleFS vs FatFS
- Troubleshooting

### 2. `examples/fatfs-test/`

Complete example project:
- `src/main.cpp` - Arduino code with FatFS operations
- `platformio.ini` - Project configuration
- `partitions.csv` - Partition table with FAT partition
- `data/test.txt` - Example file to upload
- `README.md` - Example documentation

## Usage

### Configuration in platformio.ini

```ini
[env:myenv]
board_build.filesystem = fatfs
board_build.fs_sector = 512  # Optional
```

### Available Commands

```bash
# Build FatFS image
pio run -t buildfs

# Upload FatFS image
pio run -t uploadfs

# Download FatFS image from device
pio run -t download_fatfs
```

## Technical Details

### FatFS vs LittleFS

| Aspect | LittleFS | FatFS |
|--------|----------|-------|
| Python Module | littlefs-python | fatfs-python |
| Block/Sector Size | 4096 | 512 |
| Partition Subtype | 0x83 | 0x81 |
| Build Function | build_fs_image() | build_fatfs_image() |
| Download Function | download_littlefs() | download_fatfs() |

### Implementation Details

1. **Build Process**:
   - Create RamDisk with configured size
   - Format FatFS (mkfs)
   - Mount partition
   - Copy files recursively
   - Unmount partition
   - Save RAM disk content as .bin

2. **Download Process**:
   - Read partition table from 0x8000
   - Find FAT partition (Subtype 0x81)
   - Download filesystem image
   - Create RamDisk with downloaded image
   - Mount partition
   - Extract files (limited)

## Limitations

1. **fatfs-python Library**:
   - Alpha stage (Version 0.1.2)
   - Limited API functionality
   - No complete directory traversal
   - Download extraction is basic

2. **Recommended Alternatives for Download**:
   - ESP-IDF tools
   - External FatFS tools
   - Manual extraction with other libraries

## Testing

The example project `examples/fatfs-test/` can be used for testing:

```bash
cd examples/fatfs-test
pio run -t buildfs
pio run -t uploadfs
pio run -t upload
pio device monitor
```

## Compatibility

- **ESP32**: Fully supported
- **ESP32-S2**: Fully supported
- **ESP32-S3**: Fully supported
- **ESP32-C3**: Fully supported
- **ESP32-C6**: Fully supported
- **ESP32-H2**: Fully supported

## Dependencies

- Python >= 3.10
- fatfs-python >= 0.1.2 (automatically installed)
- Cython (for fatfs-python compilation)

## Future Improvements

1. Enhanced download extraction with complete directory traversal
2. Support for FAT-specific options (FAT12/16/32)
3. Better error handling and logging
4. Performance optimizations
5. Support for file attributes and timestamps

## References

- [FatFS Documentation](http://elm-chan.org/fsw/ff/00index_e.html)
- [fatfs-python Repository](https://github.com/krakonos/fatfs-python)
- [ESP-IDF FFat Documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/storage/fatfs.html)
- [LittleFS Integration](https://github.com/Jason2866/platform-espressif32)
