# Copyright 2014-present PlatformIO <contact@platformio.org>
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
import urllib
import sys
import json
import re
import requests

from platformio.public import PlatformBase, to_unix_path


IS_WINDOWS = sys.platform.startswith("win")

class Espressif32Platform(PlatformBase):
    def configure_default_packages(self, variables, targets):
        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)

        board_config = self.board_config(variables.get("board"))
        mcu = variables.get("board_build.mcu", board_config.get("build.mcu", "esp32"))
        core_variant_board = ''.join(variables.get("board_build.extra_flags", board_config.get("build.extra_flags", "")))
        core_variant_board = core_variant_board.replace("-D", " ")
        core_variant_build = (''.join(variables.get("build_flags", []))).replace("-D", " ")
        frameworks = variables.get("pioframework", [])

        if "arduino" in frameworks:
            if "CORE32SOLO1" in core_variant_board or "FRAMEWORK_ARDUINO_SOLO1" in core_variant_build:
                # use Tasmota Esp32 solo1 framework
                self.packages["framework-arduino-solo1"]["optional"] = False
            elif "CORE32ITEAD" in core_variant_board or "FRAMEWORK_ARDUINO_ITEAD" in core_variant_build:
                # use Tasmota ESP32 ITEAD framework
                self.packages["framework-arduino-ITEAD"]["optional"] = False
            elif "FRAMEWORK_ARDUINO_ESPRESSIF" in core_variant_build and "ARDUINO_TASMOTA" not in core_variant_board:
                # use orig. espressif Arduino and IDF
                #URL = "https://raw.githubusercontent.com/espressif/arduino-esp32/idf-release/v5.1/package/package_esp32_index.template.json"
                #packjdata = requests.get(URL).json()
                #dyn_lib_url = packjdata['packages'][0]['tools'][0]['systems'][0]['url']
                #self.packages["framework-arduinoespressif32-libs"]["version"] = dyn_lib_url
                self.packages["framework-arduinoespressif32-libs"]["version"] = "https://github.com/espressif/esp32-arduino-libs/archive/refs/heads/idf-release/v5.1.zip"
                #self.packages["framework-arduinoespressif32-libs"]["version"] = "https://codeload.github.com/espressif/esp32-arduino-libs/zip/302a33cf8f23da9b734e59b8994b503a8ac0b3c0"
                self.packages["framework-arduinoespressif32-libs"]["optional"] = False
                #self.packages["framework-arduinoespressif32"]["version"] = "https://codeload.github.com/espressif/arduino-esp32/zip/bc769fd35a1d4ee26f453e9965412b7e3a8d2dc8"
                self.packages["framework-arduinoespressif32"]["version"] = "https://github.com/espressif/arduino-esp32/archive/refs/heads/master.zip"
                self.packages["framework-arduinoespressif32"]["optional"] = False
                self.packages["framework-espidf"]["owner"] = "jason2866"
                self.packages["framework-espidf"]["version"] = "https://github.com/Jason2866/esp-idf/releases/download/v5.1.3.240313/esp-idf-v5.1.3.zip" 
            elif (
                variables.get(
                    "board_build.arduino.upstream_packages",
                    board_config.get("build.arduino.upstream_packages", "no"),
                ).lower()
                == "yes"
            ):
                # fetch framework and toolchains from Arduino repo dynamically
                print("Fetch framework and toolchains from Arduino repo dynamically")
                #self.packages["framework-arduinoespressif32-libs"]["optional"] = False
                self.packages["framework-arduinoespressif32"]["version"] = "https://github.com/tasmota/arduino-esp32.git"
            else:
                # use Tasmota espressif32 framework
                self.packages["framework-arduinoespressif32"]["optional"] = False

        if "buildfs" in targets:
            filesystem = variables.get("board_build.filesystem", "littlefs")
            if filesystem == "littlefs":
                self.packages["tool-mklittlefs"]["optional"] = False
            elif filesystem == "fatfs":
                self.packages["tool-mkfatfs"]["optional"] = False
            else:
                self.packages["tool-mkspiffs"]["optional"] = False
        if variables.get("upload_protocol"):
            self.packages["tool-openocd-esp32"]["optional"] = False
        if os.path.isdir("ulp"):
            self.packages["toolchain-esp32ulp"]["optional"] = False

        if "downloadfs" in targets:
            filesystem = variables.get("board_build.filesystem", "littlefs")
            if filesystem == "littlefs":
                # Use Tasmota mklittlefs v4.0.0 to unpack, older version is incompatible
                self.packages["tool-mklittlefs"]["version"] = "~4.0.0"

        # Currently only Arduino Nano ESP32 uses the dfuutil tool as uploader
        if variables.get("board") == "arduino_nano_esp32":
            self.packages["tool-dfuutil-arduino"]["optional"] = False
        else:
            del self.packages["tool-dfuutil-arduino"]

        build_core = variables.get(
            "board_build.core", board_config.get("build.core", "arduino")
        ).lower()

        if frameworks == ["arduino"] and build_core == "esp32":
            # In case the upstream Arduino framework is specified in the configuration
            # file then we need to dynamically extract toolchain versions from the
            # Arduino index file. This feature can be disabled via a special option:
            if (
                variables.get(
                    "board_build.arduino.upstream_packages",
                    board_config.get("build.arduino.upstream_packages", "yes"),
                ).lower()
                == "yes"
            ):
                package_version = self.packages["framework-arduinoespressif32"][
                    "version"
                ]

                url_items = urllib.parse.urlparse(package_version)
                # Only GitHub repositories support dynamic packages
                if (
                    url_items.scheme in ("http", "https")
                    and url_items.netloc.startswith("github")
                    and url_items.path.endswith(".git")
                ):
                    try:
                        self.configure_upstream_arduino_packages(url_items)
                    except Exception as e:
                        sys.stderr.write(
                            "Error! Failed to extract upstream toolchain"
                            "configurations:\n%s\n" % str(e)
                        )
                        sys.stderr.write(
                            "You can disable this feature via the "
                            "`board_build.arduino.upstream_packages = no` setting in "
                            "your `platformio.ini` file.\n"
                        )
                        sys.exit(1)

        # Starting from v12, Espressif's toolchains are shipped without
        # bundled GDB. Instead, it's distributed as separate packages for Xtensa
        # and RISC-V targets.
        for gdb_package in ("tool-xtensa-esp-elf-gdb", "tool-riscv32-esp-elf-gdb"):
            self.packages[gdb_package]["optional"] = False
            if IS_WINDOWS:
                # Note: On Windows GDB v12 is not able to
                # launch a GDB server in pipe mode while v11 works fine
                self.packages[gdb_package]["version"] = "~11.2.0"

        # Common packages for IDF and mixed Arduino+IDF projects
        if "espidf" in frameworks:
            self.packages["toolchain-esp32ulp"]["optional"] = False
            for p in self.packages:
                if p in ("tool-cmake", "tool-ninja"):
                    self.packages[p]["optional"] = False
                elif p in ("tool-mconf", "tool-idf") and IS_WINDOWS:
                    self.packages[p]["optional"] = False

        for available_mcu in ("esp32", "esp32s2", "esp32s3"):
            if available_mcu == mcu:
                self.packages["toolchain-xtensa-%s" % mcu]["optional"] = False
            else:
                self.packages.pop("toolchain-xtensa-%s" % available_mcu, None)

        if mcu in ("esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c6", "esp32h2"):
            if mcu in ("esp32c2", "esp32c3", "esp32c6", "esp32h2"):
                self.packages.pop("toolchain-esp32ulp", None)
            # RISC-V based toolchain for ESP32C3, ESP32C6 ESP32S2, ESP32S3 ULP
            self.packages["toolchain-riscv32-esp"]["optional"] = False

        return super().configure_default_packages(variables, targets)

    def get_boards(self, id_=None):
        result = super().get_boards(id_)
        if not result:
            return result
        if id_:
            return self._add_dynamic_options(result)
        else:
            for key, value in result.items():
                result[key] = self._add_dynamic_options(result[key])
        return result

    def _add_dynamic_options(self, board):
        # upload protocols
        if not board.get("upload.protocols", []):
            board.manifest["upload"]["protocols"] = ["esptool", "espota"]
        if not board.get("upload.protocol", ""):
            board.manifest["upload"]["protocol"] = "esptool"

        # debug tools
        debug = board.manifest.get("debug", {})
        non_debug_protocols = ["esptool", "espota"]
        supported_debug_tools = [
            "cmsis-dap",
            "esp-prog",
            "esp-bridge",
            "iot-bus-jtag",
            "jlink",
            "minimodule",
            "olimex-arm-usb-tiny-h",
            "olimex-arm-usb-ocd-h",
            "olimex-arm-usb-ocd",
            "olimex-jtag-tiny",
            "tumpa",
        ]

        # A special case for the Kaluga board that has a separate interface config
        if board.id == "esp32-s2-kaluga-1":
            supported_debug_tools.append("ftdi")
        if board.get("build.mcu", "") in ("esp32c3", "esp32c6", "esp32s3", "esp32h2"):
            supported_debug_tools.append("esp-builtin")

        upload_protocol = board.manifest.get("upload", {}).get("protocol")
        upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
        if debug:
            upload_protocols.extend(supported_debug_tools)
        if upload_protocol and upload_protocol not in upload_protocols:
            upload_protocols.append(upload_protocol)
        board.manifest["upload"]["protocols"] = upload_protocols

        if "tools" not in debug:
            debug["tools"] = {}

        for link in upload_protocols:
            if link in non_debug_protocols or link in debug["tools"]:
                continue

            if link in ("jlink", "cmsis-dap"):
                openocd_interface = link
            elif link in ("esp-prog", "ftdi"):
                if board.id == "esp32-s2-kaluga-1":
                    openocd_interface = "ftdi/esp32s2_kaluga_v1"
                else:
                    openocd_interface = "ftdi/esp32_devkitj_v1"
            elif link == "esp-bridge":
                openocd_interface = "esp_usb_bridge"
            elif link == "esp-builtin":
                openocd_interface = "esp_usb_jtag"
            else:
                openocd_interface = "ftdi/" + link

            server_args = [
                "-s",
                "$PACKAGE_DIR/share/openocd/scripts",
                "-f",
                "interface/%s.cfg" % openocd_interface,
                "-f",
                "%s/%s"
                % (
                    ("target", debug.get("openocd_target"))
                    if "openocd_target" in debug
                    else ("board", debug.get("openocd_board"))
                ),
            ]

            debug["tools"][link] = {
                "server": {
                    "package": "tool-openocd-esp32",
                    "executable": "bin/openocd",
                    "arguments": server_args,
                },
                "init_break": "thb app_main",
                "init_cmds": [
                    "define pio_reset_halt_target",
                    "   monitor reset halt",
                    "   flushregs",
                    "end",
                    "define pio_reset_run_target",
                    "   monitor reset",
                    "end",
                    "target extended-remote $DEBUG_PORT",
                    "$LOAD_CMDS",
                    "pio_reset_halt_target",
                    "$INIT_BREAK",
                ],
                "onboard": link in debug.get("onboard_tools", []),
                "default": link == debug.get("default_tool"),
            }

            # Avoid erasing Arduino Nano bootloader by preloading app binary
            if board.id == "arduino_nano_esp32":
                debug["tools"][link]["load_cmds"] = "preload"
        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, debug_config):
        build_extra_data = debug_config.build_data.get("extra", {})
        flash_images = build_extra_data.get("flash_images", [])

        if "openocd" in (debug_config.server or {}).get("executable", ""):
            debug_config.server["arguments"].extend(
                ["-c", "adapter speed %s" % (debug_config.speed or "5000")]
            )

        ignore_conds = [
            debug_config.load_cmds != ["load"],
            not flash_images,
            not all([os.path.isfile(item["path"]) for item in flash_images]),
        ]

        if any(ignore_conds):
            return

        load_cmds = [
            'monitor program_esp "{{{path}}}" {offset} verify'.format(
                path=to_unix_path(item["path"]), offset=item["offset"]
            )
            for item in flash_images
        ]
        load_cmds.append(
            'monitor program_esp "{%s.bin}" %s verify'
            % (
                to_unix_path(debug_config.build_data["prog_path"][:-4]),
                build_extra_data.get("application_offset", "0x10000"),
            )
        )
        debug_config.load_cmds = load_cmds


    @staticmethod
    def extract_toolchain_versions(tool_deps):
        def _parse_version(original_version):
            assert original_version
            version_patterns = (
                r"^gcc(?P<MAJOR>\d+)_(?P<MINOR>\d+)_(?P<PATCH>\d+)-esp-(?P<EXTRA>.+)$",
                r"^esp-(?P<EXTRA>.+)-(?P<MAJOR>\d+)\.(?P<MINOR>\d+)\.?(?P<PATCH>\d+)$",
                r"^esp-(?P<MAJOR>\d+)\.(?P<MINOR>\d+)\.(?P<PATCH>\d+)(_(?P<EXTRA>.+))?$",
                r"^idf-release_v(?P<MAJOR>\d+)\.(?P<MINOR>\d+)(.(?P<PATCH>\d+))?(-(?P<EXTRA>.+))?$",
            )
            for pattern in version_patterns:
                match = re.search(pattern, original_version)
                if match:
                    result = "%s.%s.%s" % (
                        match.group("MAJOR"),
                        match.group("MINOR"),
                        match.group("PATCH") if match.group("PATCH") is not None else "0",
                    )
                    if match.group("EXTRA"):
                        result = result + "+%s" % match.group("EXTRA")
                    return result

            raise ValueError("Bad package version `%s`" % original_version)

        if not tool_deps:
            raise ValueError(
                ("Failed to extract tool dependencies from the remote package file")
            )

        toolchain_remap = {
            "esp32-arduino-libs": "framework-arduinoespressif32-libs",
            "xtensa-esp32-elf-gcc": "toolchain-xtensa-esp32",
            "xtensa-esp32s2-elf-gcc": "toolchain-xtensa-esp32s2",
            "xtensa-esp32s3-elf-gcc": "toolchain-xtensa-esp32s3",
            "riscv32-esp-elf-gcc": "toolchain-riscv32-esp",
        }

        result = dict()
        for tool in tool_deps:
            if tool["name"] in toolchain_remap:
                result[toolchain_remap[tool["name"]]] = _parse_version(tool["version"])

        return result

    @staticmethod
    def parse_tool_dependencies(index_data):
        for package in index_data.get("packages", []):
            if package["name"] == "esp32":
                for platform in package["platforms"]:
                    if platform["name"] == "esp32":
                        return platform["toolsDependencies"]

        return []

    @staticmethod
    def download_remote_package_index(url_items):
        def _prepare_url_for_index_file(url_items):
            tag = "master"
            if url_items.fragment:
                tag = url_items.fragment
            return (
                "https://raw.githubusercontent.com/%s/"
                "%s/package/package_esp32_index.template.json"
                % (url_items.path.replace(".git", ""), tag)
            )

        index_file_url = _prepare_url_for_index_file(url_items)

        try:
            from platformio.public import fetch_http_content
            content = fetch_http_content(index_file_url)
        except ImportError:
            import requests
            content = requests.get(index_file_url, timeout=5).text

        return json.loads(content)

    def configure_arduino_toolchains(self, package_index):
        if not package_index:
            return

        toolchain_packages = self.extract_toolchain_versions(
            self.parse_tool_dependencies(package_index)
        )
        for toolchain_package, version in toolchain_packages.items():
            if toolchain_package not in self.packages:
                self.packages[toolchain_package] = dict()
            self.packages[toolchain_package]["version"] = version
            self.packages[toolchain_package]["owner"] = "espressif"
            self.packages[toolchain_package]["type"] = "toolchain"
            if (toolchain_package == "framework-arduinoespressif32-libs"):
                self.packages[toolchain_package]["optional"] = False

    def configure_upstream_arduino_packages(self, url_items):
        framework_index_file = os.path.join(
            self.get_package_dir("framework-arduinoespressif32") or "",
            "package",
            "package_esp32_index.template.json",
        )

        # Detect whether the remote is already cloned
        if os.path.isfile(framework_index_file) and os.path.isdir(
            os.path.join(
                self.get_package_dir("framework-arduinoespressif32") or "", ".git"
            )
        ):
            with open(framework_index_file) as fp:
                self.configure_arduino_toolchains(json.load(fp))
        else:
            print("Configuring toolchain packages from a remote source...")
            self.configure_arduino_toolchains(
                self.download_remote_package_index(url_items)
            )
