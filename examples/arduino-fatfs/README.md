# FatFS Test Example

This example demonstrates the FatFS integration in platform-espressif32.

## Features

- Mount FatFS and display information
- List files and directories
- Read, write, and append files
- Delete files
- Upload files from the `data/` directory

## Usage

### 1. Compile Project

```bash
pio run
```

### 2. Build and Upload FatFS Image

```bash
# Build image from data/ directory
pio run -t buildfs

# Upload image to ESP32
pio run -t uploadfs
```

### 3. Upload Firmware

```bash
pio run -t upload
```

### 4. Open Serial Monitor

```bash
pio device monitor
```

## Expected Output

```
=== FatFS Test ===

FFat Size: 1 MB
FFat Used: 0 MB
FFat Free: 1 MB

Listing directory: /
  FILE: /test.txt  SIZE: 123

Reading file: /test.txt
Read from file: Hello FatFS!
This file was uploaded from the data directory.
FatFS integration is working correctly.

Writing file: /hello.txt
File written
Reading file: /hello.txt
Read from file: Hello from ESP32!

Appending to file: /hello.txt
Message appended
Reading file: /hello.txt
Read from file: Hello from ESP32!
This is appended text.

Deleting file: /hello.txt
File deleted

Final directory listing:
Listing directory: /
  FILE: /test.txt  SIZE: 123

=== Test Complete ===
```

## Download FatFS from Device

```bash
pio run -t download_fatfs
```

Files will be extracted to the `unpacked_fs/` directory.

## Notes

- The partition table must contain a FAT partition (see `partitions.csv`)
- FatFS uses 512-byte sectors by default
- The partition should be at least 1 MB in size
