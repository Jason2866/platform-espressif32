How to build PlatformIO based project
=====================================


```shell
# Change directory to example
$ cd platform-espressif32/examples/arduino-nimble-advertising

# Build project
$ pio run

# Upload firmware
$ pio run --target upload

# Build specific environment
$ pio run -e esp32-c6-devkitc-1

# Upload firmware for the specific environment
$ pio run -e esp32-c6-devkitc-1 --target upload

# Clean build files
$ pio run --target clean
```