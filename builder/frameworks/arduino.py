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

pm = ToolPackageManager()

extra_flags = ''.join([element.replace("-D", " ") for element in board.get("build.extra_flags", "")])
build_flags = ''.join([element.replace("-D", " ") for element in env.GetProjectOption("build_flags")])

SConscript("_embed_files.py", exports="env")

flag_custom_sdkonfig = False
if config.has_option("env:"+env["PIOENV"], "custom_sdkconfig"):
    flag_custom_sdkonfig = True

if ("CORE32SOLO1" in extra_flags or "FRAMEWORK_ARDUINO_SOLO1" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")) and flag_custom_sdkonfig == False:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-solo1")
elif ("CORE32ITEAD" in extra_flags or "FRAMEWORK_ARDUINO_ITEAD" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")) and flag_custom_sdkonfig == False:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-ITEAD")
elif "arduino" in env.subst("$PIOFRAMEWORK") and "CORE32SOLO1" not in extra_flags and "FRAMEWORK_ARDUINO_SOLO1" not in build_flags and "CORE32ITEAD" not in extra_flags and "FRAMEWORK_ARDUINO_ITEAD" not in build_flags:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
elif "arduino" in env.subst("$PIOFRAMEWORK") and flag_custom_sdkonfig == True:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")

def any_custom_sdkconfig(any_sdkconfig):
    # Search if any custom sdkconfig.<env> exist.
    any_sdkconfig = False
    files_lib = "".join([f for f in os.listdir(join(FRAMEWORK_DIR,"tools","esp32-arduino-libs")) if os.path.isfile(f)])
    if "sdkconfig" in files_lib:
        any_sdkconfig = True
    return any_sdkconfig

def check_reinstall_frwrk(frwrk_reinstall):
    frwrk_reinstall = False
    cust_sdk = False
    cust_sdk = any_custom_sdkconfig(cust_sdk)
    print("Custom sdkconfig is", cust_sdk)
    if flag_custom_sdkonfig == False and cust_sdk == True:
        # case custom sdkconfig exists and a env without "custom_sdkconfig"
        frwrk_reinstall = True
    # hack: overwrite boards info "url" entry with info framework needs reinstall
    board.update("url", frwrk_reinstall)
    print("Board url entry updated to:", board.get("url", ""))
    return frwrk_reinstall

dummy = True
print("Test: Needs framework reinstall:", check_reinstall_frwrk(dummy))

ARDUINO_FRMWRK_URL = (platform.get_package_spec("framework-arduinoespressif32"))split("uri",1)[1]
print("Arduino Framework URL", ARDUINO_FRMWRK_URL)

if board.get("url", "") == True:
    shutil.rmtree(FRAMEWORK_DIR)
    pm.install("https://github.com/Jason2866/esp32-arduino-lib-builder/releases/download/3005/framework-arduinoespressif32-all-release_v5.3-22a3b096.zip")

if flag_custom_sdkonfig == True:
    # check if matching custom libs are already there
    custom_lib_config = join(platform.get_package_dir("framework-arduinoespressif32"),"tools","esp32-arduino-libs","sdkconfig."+env["PIOENV"])
    if bool(os.path.isfile(custom_lib_config)):
        flag_custom_sdkonfig = False
        # current env matches customized sdkconfig -> correct framework to use
    else:
        flag_custom_sdkonfig = True
        # current env forces custom libs -> Build of libs is needed

if flag_custom_sdkonfig == True:
    if env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("False", "Inactive"):
        print("Compile Arduino IDF libs for %s" % env["PIOENV"])
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
