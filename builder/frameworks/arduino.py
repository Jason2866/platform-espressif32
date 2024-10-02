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
from os.path import join

from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment, SConscript
from platformio.package.version import pepver_to_semver

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")

extra_flags = ''.join([element.replace("-D", " ") for element in env.BoardConfig().get("build.extra_flags", "")])
build_flags = ''.join([element.replace("-D", " ") for element in env.GetProjectOption("build_flags")])

SConscript("_embed_files.py", exports="env")

if ("CORE32SOLO1" in extra_flags or "FRAMEWORK_ARDUINO_SOLO1" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")):
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-solo1")
elif ("CORE32ITEAD" in extra_flags or "FRAMEWORK_ARDUINO_ITEAD" in build_flags) and ("arduino" in env.subst("$PIOFRAMEWORK")):
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-ITEAD")
elif "arduino" in env.subst("$PIOFRAMEWORK") and "CORE32SOLO1" not in extra_flags and "FRAMEWORK_ARDUINO_SOLO1" not in build_flags and "CORE32ITEAD" not in extra_flags and "FRAMEWORK_ARDUINO_ITEAD" not in build_flags:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
ARDUINO_FRAMEWORK_DIR = FRAMEWORK_DIR

flag_custom_sdkonfig = False
try:
    if env.GetProjectOption("custom_sdkconfig"):
        flag_custom_sdkonfig = True
except:
    flag_custom_sdkonfig = False

print("Arduino libs compile flag", env.subst("$ARDUINO_LIB_COMPILE_FLAG"))
if flag_custom_sdkonfig:
    if env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("False", "Inactive"):
        print("Arduino IDF libs compile")
        print("arduino.py script calling SConscript espidf.py")
        print("Pio framework", env.subst("$PIOFRAMEWORK"))
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

if "espidf" not in env.subst("$PIOFRAMEWORK") and env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("Inactive", "True"):
    print("Arduino compile")
    print("Pio framework", env.subst("$PIOFRAMEWORK"))
    print("arduino.py script calling SConscript platformio-build.py")
    if env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("True"):
        env.Replace(
            BUILD_FLAGS=env.subst("$ORIG_BUILD_FLAGS"),
            BUILD_UNFLAGS=env.subst("$ORIG_BUILD_UNFLAGS"),
            LINKFLAGS=env.subst("$ORIG_LINKFLAGS"),
            PROJECT_SRC_DIR=env.subst("$ORIG_PROJECT_SRC_DIR"),
        )
        print("Arduino: Source Dir", env.subst("$PROJECT_SRC_DIR"))
        print("Arduino: Build Flags", env.subst("$BUILD_FLAGS"))
        print("Arduino: Build UnFlags", env.subst("$BUILD_UNFLAGS"))
        print("Arduino: Link flags", env.subst("$LINKFLAGS"))
        def esp32_copy_new_arduino_libs(env):
            print("Copy compiled IDF libraries to Arduino framework")
            lib_src = join(env["PROJECT_BUILD_DIR"],env["PIOENV"],"esp-idf")
            lib_dst = join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"lib")
            src = [join(lib_src,x) for x in os.listdir(lib_src)]
            src = [folder for folder in src if not os.path.isfile(folder)] # folders only
            for folder in src:
                # print(folder)
                files = [join(folder,x) for x in os.listdir(folder)]
                for file in files:
                    if file.strip().endswith(".a"):
                        # print(file.split("/")[-1])
                        shutil.copyfile(file,join(lib_dst,file.split("/")[-1]))
            if not bool(os.path.isfile(join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig.orig"))):
                shutil.move(join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig"),join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig.orig"))
            shutil.copyfile(join(env.subst("$PROJECT_DIR"),"sdkconfig."+env["PIOENV"]),join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig"))

    install_python_deps()
    SConscript(join(FRAMEWORK_DIR, "tools", "platformio-build.py"))
    
