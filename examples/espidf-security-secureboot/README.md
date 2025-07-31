How to build PlatformIO based project
=====================================

1. Follow the instructions on how to enable [Secure Boot](https://docs.platformio.org/en/latest/frameworks/espidf.html#secure-bootloader) 
2. Run these commands:

```shell
# Change directory to example
$ cd platform-espressif32/examples/espidf-security-secureboot

# Build project
$ pio run

# Upload firmware
$ pio run --target upload
```