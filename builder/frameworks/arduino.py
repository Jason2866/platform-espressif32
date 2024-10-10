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

"""
Arduino

Arduino Wiring-based Framework allows writing cross-platform software to
control devices attached to a wide range of Arduino boards to create all
kinds of creative coding, interactive objects, spaces or physical experiences.

http://arduino.cc/en/Reference/HomePage
"""

import subprocess
import json
import semantic_version
import os
import shutil
from os.path import join

from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment, SConscript
from platformio.package.version import pepver_to_semver
from platformio.project.config import ProjectConfig
from platformio.package.manager.tool import ToolPackageManager

env = DefaultEnvironment()
platform = env.PioPlatform()
config = env.GetProjectConfig()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")
flag_custom_sdkconfig = config.has_option("env:"+env["PIOENV"], "custom_sdkconfig")
framework_reinstall = False

extra_flags = ''.join([element.replace("-D", " ") for element in board.get("build.extra_flags", "")])
build_flags = ''.join([element.replace("-D", " ") for element in env.GetProjectOption("build_flags")])
pm = ToolPackageManager()

SConscript("_embed_files.py", exports="env")

if ("CORE32SOLO1" in extra_flags or "FRAMEWORK_ARDUINO_SOLO1" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")) and flag_custom_sdkconfig == False:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-solo1")
elif ("CORE32ITEAD" in extra_flags or "FRAMEWORK_ARDUINO_ITEAD" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")) and flag_custom_sdkconfig == False:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-ITEAD")
elif "arduino" in env.subst("$PIOFRAMEWORK") and "CORE32SOLO1" not in extra_flags and "FRAMEWORK_ARDUINO_SOLO1" not in build_flags and "CORE32ITEAD" not in extra_flags and "FRAMEWORK_ARDUINO_ITEAD" not in build_flags:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
elif "arduino" in env.subst("$PIOFRAMEWORK") and flag_custom_sdkconfig == True:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")

def get_MD5_hash(phrase):
    import hashlib
    return hashlib.md5((phrase).encode('utf-8')).hexdigest()[:16]


def matching_custom_sdkconfig():
    # check if current env is matching to existing sdkconfig
    cust_sdk_is_present = False
    matching_sdkconfig = False
    last_sdkconfig_path = join(env.subst("$PROJECT_DIR"),"sdkconfig.defaults")
    if os.path.exists(last_sdkconfig_path) == False:
        return matching_sdkconfig, cust_sdk_is_present
    print(last_sdkconfig_path)
    with open(last_sdkconfig_path) as src:
        line = src.readline()
        if line.startswith("# TASMOTA__"):
            cust_sdk_is_present = True;
            costum_options = env.GetProjectOption("custom_sdkconfig")
            print(costum_options)
            if (line.split("__")[1]).strip() == (get_MD5_hash(costum_options).strip()):
                matching_sdkconfig = True
                # print(line.split("__")[1], get_MD5_hash(costum_options))

    return matching_sdkconfig, cust_sdk_is_present

def check_reinstall_frwrk():
    framework_reinstall = False
    matching_sdkconfig, cust_sdk_is_present = matching_custom_sdkconfig()
    print("*** Custom sdkconfig in config", flag_custom_sdkconfig)
    print("*** Custom sdkconfig is present", cust_sdk_is_present)
    print("*** sdkconfig is matching", matching_sdkconfig)
    if flag_custom_sdkconfig == False and cust_sdk_is_present == True:
        # case custom sdkconfig exists and a env without "custom_sdkconfig"
        framework_reinstall = True
    if flag_custom_sdkconfig == True and cust_sdk_is_present == True and matching_sdkconfig == False:
        # check if current custom sdkconfig is differnet from existing
        framework_reinstall = True
    # print("Framework Reinstall is", framework_reinstall)
    return framework_reinstall

if check_reinstall_frwrk() == True:
    print("*** Reinstall Arduino framework ***")
    shutil.rmtree(FRAMEWORK_DIR)
    ARDUINO_FRMWRK_URL = str(platform.get_package_spec("framework-arduinoespressif32")).split("uri=",1)[1][:-1]
    pm.install(ARDUINO_FRMWRK_URL)

if flag_custom_sdkconfig == True:
    if env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("False", "Inactive"):
        print("*** Compile Arduino IDF libs for %s ***" % env["PIOENV"])
        SConscript("espidf.py")

def install_python_deps():
    def _get_installed_pip_packages():
        result = {}
        packages = {}
        pip_output = subprocess.check_output(
            [
                env.subst("$PYTHONEXE"),
                "-m",
                "pip",
                "list",
                "--format=json",
                "--disable-pip-version-check",
            ]
        )
        try:
            packages = json.loads(pip_output)
        except:
            print("Warning! Couldn't extract the list of installed Python packages.")
            return {}
        for p in packages:
            result[p["name"]] = pepver_to_semver(p["version"])

        return result

    deps = {
        "wheel": ">=0.35.1",
        "zopfli": ">=0.2.2",
        "tasmota-metrics": ">=0.4.3"
    }

    installed_packages = _get_installed_pip_packages()
    packages_to_install = []
    for package, spec in deps.items():
        if package not in installed_packages:
            packages_to_install.append(package)
        else:
            version_spec = semantic_version.Spec(spec)
            if not version_spec.match(installed_packages[package]):
                packages_to_install.append(package)

    if packages_to_install:
        env.Execute(
            env.VerboseAction(
                (
                    '"$PYTHONEXE" -m pip install -U '
                    + " ".join(
                        [
                            '"%s%s"' % (p, deps[p])
                            for p in packages_to_install
                        ]
                    )
                ),
                "Installing Arduino Python dependencies",
            )
        )
    return

if "arduino" in env.subst("$PIOFRAMEWORK") and "espidf" not in env.subst("$PIOFRAMEWORK") and env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("Inactive", "True"):
    install_python_deps()
    SConscript(join(FRAMEWORK_DIR, "tools", "platformio-build.py"))
