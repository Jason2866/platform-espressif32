# Copyright (c) 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import subprocess
import sys
import glob

from platformio.compat import IS_WINDOWS
from platformio.exception import PlatformioException
from platformio.public import (
    DeviceMonitorFilterBase,
    load_build_metadata,
)
from platformio import fs
from platformio.project.config import ProjectConfig
from platformio.platform.factory import PlatformFactory

# By design, __init__ is called inside miniterm and we can't pass context to it.
# pylint: disable=attribute-defined-outside-init


class Esp32ExceptionDecoder(DeviceMonitorFilterBase):
    NAME = "esp32_exception_decoder"

    # More specific pattern for PC:SP pairs in backtraces
    ADDR_PATTERN = re.compile(r"((?:0x[0-9a-fA-F]{8}:0x[0-9a-fA-F]{8}(?: |$))+)")
    ADDR_SPLIT = re.compile(r"[ :]")
    PREFIX_RE = re.compile(r"^ *")
    
    # Patterns that indicate we're in an exception/backtrace context
    BACKTRACE_KEYWORDS = re.compile(
        r"(Backtrace:|"
        r"abort\(\) was called at PC|"
        r"Guru Meditation Error:|"
        r"panic'ed|"
        r"register dump:|"
        r"Stack smashing protect failure!|"
        r"CORRUPT HEAP:|"
        r"assertion .* failed:|"
        r"Debug exception reason:|"
        r"Undefined behavior of type)",
        re.IGNORECASE
    )

    # Chip name mapping for ROM ELF files
    CHIP_NAME_MAP = {
        "esp32": "esp32",
        "esp32s2": "esp32s2",
        "esp32s3": "esp32s3",
        "esp32c2": "esp32c2",
        "esp32c3": "esp32c3",
        "esp32c6": "esp32c6",
        "esp32h2": "esp32h2",
        "esp32p4": "esp32p4",
    }

    def __call__(self):
        self.buffer = ""
        self.in_backtrace_context = False
        self.lines_since_context = 0
        self.max_context_lines = 50  # Maximum lines to process after context keyword

        self.firmware_path = None
        self.addr2line_path = None
        self.rom_elf_path = None
        self.enabled = self.setup_paths()

        if self.config.get("env:" + self.environment, "build_type") != "debug":
            print(
                """
Please build project in debug configuration to get more details about an exception.
See https://docs.platformio.org/page/projectconf/build_configurations.html

"""
            )

        return self

    def get_chip_name(self, data):
        """
        Determine chip name from build metadata.
        Tries multiple methods to detect the chip type.
        """
        # Try to get from board definition
        board = data.get("board", "").lower()
        
        # Check if board name contains chip identifier
        for chip_key in self.CHIP_NAME_MAP.keys():
            if chip_key in board:
                return self.CHIP_NAME_MAP[chip_key]
        
        # Try to get from MCU
        mcu = data.get("mcu", "").lower()
        for chip_key in self.CHIP_NAME_MAP.keys():
            if chip_key in mcu:
                return self.CHIP_NAME_MAP[chip_key]
        
        # Default to esp32 if not found
        return "esp32"

    def find_rom_elf(self, chip_name):
        """
        Find the appropriate ROM ELF file for the chip.
        Uses platform.get_package_dir() to access tool-esp-rom-elfs.
        """
        try:
            # Get platform instance from project config
            platform_name = self.config.get("env:" + self.environment, "platform")
            
            # Handle platform with version/repository specification
            if "@" in platform_name:
                platform_name = platform_name.split("@")[0]
            
            # Get platform instance
            platform = PlatformFactory.new(platform_name)
            
            # Ensure tool-esp-rom-elfs is installed
            platform.ensure_tool_installed("tool-esp-rom-elfs")
            
            # Get package directory via platform
            rom_elfs_dir = platform.get_package_dir("tool-esp-rom-elfs")
            
            if not rom_elfs_dir or not os.path.isdir(rom_elfs_dir):
                sys.stderr.write(
                    "%s: ROM ELFs directory not found\n"
                    % self.__class__.__name__
                )
                return None
            
            # Search for ROM ELF files matching the chip
            # Pattern: <chip_name>_rev<rev>_rom.elf
            pattern = os.path.join(rom_elfs_dir, f"{chip_name}_rev*.elf")
            rom_files = glob.glob(pattern)
            
            if not rom_files:
                sys.stderr.write(
                    "%s: No ROM ELF files found for chip %s in %s\n"
                    % (self.__class__.__name__, chip_name, rom_elfs_dir)
                )
                return None
            
            # Sort by revision number and return the lowest (most compatible)
            # This handles cases where specific revision isn't available
            rom_files.sort()
            return rom_files[0]
            
        except Exception as e:
            sys.stderr.write(
                "%s: Error accessing ROM ELF package: %s\n"
                % (self.__class__.__name__, e)
            )
            return None

    def setup_paths(self):
        self.project_dir = os.path.abspath(self.project_dir)
        try:
            data = load_build_metadata(self.project_dir, self.environment, cache=True)

            self.firmware_path = data["prog_path"]
            if not os.path.isfile(self.firmware_path):
                sys.stderr.write(
                    "%s: firmware at %s does not exist, rebuild the project?\n"
                    % (self.__class__.__name__, self.firmware_path)
                )
                return False

            cc_path = data.get("cc_path", "")
            if "-gcc" in cc_path:
                path = cc_path.replace("-gcc", "-addr2line")
                if os.path.isfile(path):
                    self.addr2line_path = path
            elif "-clang" in cc_path:
                # Support for Clang toolchain
                path = cc_path.replace("-clang", "-addr2line")
                if os.path.isfile(path):
                    self.addr2line_path = path
            
            if not self.addr2line_path:
                sys.stderr.write(
                    "%s: disabling, failed to find addr2line.\n" % self.__class__.__name__
                )
                return False
            
            # Try to find ROM ELF file
            chip_name = self.get_chip_name(data)
            self.rom_elf_path = self.find_rom_elf(chip_name)
            
            if self.rom_elf_path:
                sys.stderr.write(
                    "%s: ROM ELF found at %s\n" 
                    % (self.__class__.__name__, self.rom_elf_path)
                )
            else:
                sys.stderr.write(
                    "%s: ROM ELF not found for chip %s, ROM addresses will not be decoded\n"
                    % (self.__class__.__name__, chip_name)
                )
            
            return True
            
        except PlatformioException as e:
            sys.stderr.write(
                "%s: disabling, exception while looking for addr2line: %s\n"
                % (self.__class__.__name__, e)
            )
            return False

    def is_backtrace_context(self, line):
        """Check if the line indicates we're entering a backtrace context."""
        return self.BACKTRACE_KEYWORDS.search(line) is not None

    def should_process_line(self, line):
        """
        Determine if a line should be processed for address decoding.
        Returns True only if:
        1. We're in a backtrace context, OR
        2. The line itself contains backtrace keywords
        """
        # Check if this line starts a backtrace context
        if self.is_backtrace_context(line):
            self.in_backtrace_context = True
            self.lines_since_context = 0
            return True
        
        # If we're in context, track how many lines we've processed
        if self.in_backtrace_context:
            self.lines_since_context += 1
            
            # Exit context after max_context_lines or if we see an empty line
            if self.lines_since_context > self.max_context_lines or line.strip() == "":
                self.in_backtrace_context = False
                return False
            
            return True
        
        return False

    def rx(self, text):
        if not self.enabled:
            return text

        last = 0
        while True:
            idx = text.find("\n", last)
            if idx == -1:
                if len(self.buffer) < 4096:
                    self.buffer += text[last:]
                break

            line = text[last:idx]
            if self.buffer:
                line = self.buffer + line
                self.buffer = ""
            last = idx + 1

            # Only process line if it's in the right context
            if not self.should_process_line(line):
                continue

            m = self.ADDR_PATTERN.search(line)
            if m is None:
                continue

            trace = self.build_backtrace(line, m.group(1))
            if trace:
                text = text[: idx + 1] + trace + text[idx + 1 :]
                last += len(trace)
        return text

    def is_address_ignored(self, address):
        return address in ("", "0x00000000")

    def filter_addresses(self, addresses_str):
        addresses = self.ADDR_SPLIT.split(addresses_str)
        size = len(addresses)
        while size > 1 and self.is_address_ignored(addresses[size-1]):
            size -= 1
        return addresses[:size]

    def decode_address(self, addr, elf_path):
        """
        Decode a single address using addr2line.
        Returns the decoded string or None if decoding failed.
        """
        enc = "mbcs" if IS_WINDOWS else "utf-8"
        args = [self.addr2line_path, u"-fipC", u"-e", elf_path, addr]
        
        try:
            output = (
                subprocess.check_output(args)
                .decode(enc)
                .strip()
            )
            
            # newlines happen with inlined methods
            output = output.replace("\n", "\n     ")
            
            # Check if address was found in ELF
            if output == "?? ??:0":
                return None
            
            return output
            
        except subprocess.CalledProcessError:
            return None

    def build_backtrace(self, line, address_match):
        addresses = self.filter_addresses(address_match)
        if not addresses:
            return ""

        prefix_match = self.PREFIX_RE.match(line)
        prefix = prefix_match.group(0) if prefix_match is not None else ""

        trace = ""
        try:
            i = 0
            for addr in addresses:
                # First try to decode with application ELF
                output = self.decode_address(addr, self.firmware_path)
                is_rom = False
                
                # If not found in app ELF, try ROM ELF
                if output is None and self.rom_elf_path:
                    output = self.decode_address(addr, self.rom_elf_path)
                    if output is not None:
                        is_rom = True
                
                # Skip if address couldn't be decoded
                if output is None:
                    continue

                output = self.strip_project_dir(output)
                
                # Add "in ROM" suffix for ROM addresses
                if is_rom:
                    # Extract function name (first part before "at")
                    parts = output.split(" at ", 1)
                    if len(parts) == 2:
                        output = f"{parts[0]} in ROM"
                    else:
                        output = f"{output} in ROM"
                
                trace += "%s  #%-2d %s in %s\n" % (prefix, i, addr, output)
                i += 1
                
        except subprocess.CalledProcessError as e:
            sys.stderr.write(
                "%s: failed to call %s: %s\n"
                % (self.__class__.__name__, self.addr2line_path, e)
            )

        return trace + "\n" if trace else ""

    def strip_project_dir(self, trace):
        while True:
            idx = trace.find(self.project_dir)
            if idx == -1:
                break
            trace = trace[:idx] + trace[idx + len(self.project_dir) + 1 :]
        return trace
