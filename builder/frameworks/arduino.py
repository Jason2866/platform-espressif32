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
import sys
import shutil
import hashlib
from os.path import join, exists, isabs, splitdrive, commonpath, relpath

from SCons.Script import DefaultEnvironment, SConscript
from platformio import fs
from platformio.package.version import pepver_to_semver
from platformio.package.manager.tool import ToolPackageManager

# Constants for better performance
UNICORE_FLAGS = {
    "CORE32SOLO1",
    "CONFIG_FREERTOS_UNICORE=y"
}

# Cache class for frequently used paths
class PathCache:
    def __init__(self, platform, mcu):
        self.platform = platform
        self.mcu = mcu
        self._framework_dir = None
        self._sdk_dir = None
    
    @property
    def framework_dir(self):
        if self._framework_dir is None:
            self._framework_dir = self.platform.get_package_dir("framework-arduinoespressif32")
        return self._framework_dir
    
    @property 
    def sdk_dir(self):
        if self._sdk_dir is None:
            self._sdk_dir = fs.to_unix_path(
                join(self.framework_dir, "tools", "esp32-arduino-libs", self.mcu, "include")
            )
        return self._sdk_dir

# Initialization
env = DefaultEnvironment()
pm = ToolPackageManager()
platform = env.PioPlatform()
config = env.GetProjectConfig()
board = env.BoardConfig()

# Cached values
mcu = board.get("build.mcu", "esp32")
pioenv = env["PIOENV"]
project_dir = env.subst("$PROJECT_DIR")
path_cache = PathCache(platform, mcu)

# Board configuration
board_sdkconfig = board.get("espidf.custom_sdkconfig", "")
entry_custom_sdkconfig = "\n"
flag_custom_sdkconfig = False
IS_WINDOWS = sys.platform.startswith("win")

# Custom SDKConfig check
current_env_section = f"env:{pioenv}"
if config.has_option(current_env_section, "custom_sdkconfig"):
    entry_custom_sdkconfig = env.GetProjectOption("custom_sdkconfig")
    flag_custom_sdkconfig = True

if len(board_sdkconfig) > 2:
    flag_custom_sdkconfig = True

extra_flags_raw = board.get("build.extra_flags", [])
if isinstance(extra_flags_raw, list):
    extra_flags = " ".join(extra_flags_raw).replace("-D", " ")
else:
    extra_flags = str(extra_flags_raw).replace("-D", " ")

framework_reinstall = False

FRAMEWORK_DIR = path_cache.framework_dir

SConscript("_embed_files.py", exports="env")

flag_any_custom_sdkconfig = exists(join(FRAMEWORK_DIR, "tools", "esp32-arduino-libs", "sdkconfig"))

# Optimized Esp32-solo1 libs settings
if flag_custom_sdkconfig and any(flag in extra_flags or flag in entry_custom_sdkconfig 
                                or flag in board_sdkconfig for flag in UNICORE_FLAGS):
    if len(str(env.GetProjectOption("build_unflags"))) == 2:  # No valid env, needs init
        env['BUILD_UNFLAGS'] = {}
    
    build_unflags = " ".join(env['BUILD_UNFLAGS']) + " -mdisable-hardware-atomics -ustart_app_other_cores"
    new_build_unflags = build_unflags.split()
    env.Replace(BUILD_UNFLAGS=new_build_unflags)

def get_packages_to_install(deps, installed_packages):
    """Generator for packages to install"""
    for package, spec in deps.items():
        if package not in installed_packages:
            yield package
        else:
            version_spec = semantic_version.Spec(spec)
            if not version_spec.match(installed_packages[package]):
                yield package

def install_python_deps():
    def _get_installed_pip_packages():
        result = {}
        try:
            pip_output = subprocess.check_output([
                env.subst("$PYTHONEXE"),
                "-m", "pip", "list", "--format=json", "--disable-pip-version-check"
            ])
            packages = json.loads(pip_output)
            for p in packages:
                result[p["name"]] = pepver_to_semver(p["version"])
        except Exception:
            print("Warning! Couldn't extract the list of installed Python packages.")
        
        return result

    deps = {
        "wheel": ">=0.35.1",
        "rich-click": ">=1.8.6",
        "zopfli": ">=0.2.2",
        "esp-idf-size": ">=1.6.1"
    }

    installed_packages = _get_installed_pip_packages()
    packages_to_install = list(get_packages_to_install(deps, installed_packages))

    if packages_to_install:
        packages_str = " ".join(f'"{p}{deps[p]}"' for p in packages_to_install)
        env.Execute(
            env.VerboseAction(
                f'"$PYTHONEXE" -m pip install -U -q -q -q {packages_str}',
                "Installing Arduino Python dependencies",
            )
        )

install_python_deps()

def get_MD5_hash(phrase):
    return hashlib.md5(phrase.encode('utf-8')).hexdigest()[:16]

def matching_custom_sdkconfig():
    """Checks if current environment matches existing sdkconfig"""
    cust_sdk_is_present = False
    
    if not flag_any_custom_sdkconfig:
        return True, cust_sdk_is_present
        
    last_sdkconfig_path = join(project_dir, "sdkconfig.defaults")
    if not exists(last_sdkconfig_path):
        return False, cust_sdk_is_present
        
    if not flag_custom_sdkconfig:
        return False, cust_sdk_is_present
    
    try:
        with open(last_sdkconfig_path) as src:
            line = src.readline()
            if line.startswith("# TASMOTA__"):
                cust_sdk_is_present = True
                custom_options = entry_custom_sdkconfig
                expected_hash = get_MD5_hash(custom_options.strip() + mcu)
                if line.split("__")[1].strip() == expected_hash:
                    return True, cust_sdk_is_present
    except (IOError, IndexError):
        pass

    return False, cust_sdk_is_present

def check_reinstall_frwrk():
    if not flag_custom_sdkconfig and flag_any_custom_sdkconfig:
        # case custom sdkconfig exists and an env without "custom_sdkconfig"
        return True
    
    if flag_custom_sdkconfig:
        matching_sdkconfig, _ = matching_custom_sdkconfig()
        if not matching_sdkconfig:
            # check if current custom sdkconfig is different from existing
            return True
    
    return False

def call_compile_libs():
    print(f"*** Compile Arduino IDF libs for {pioenv} ***")
    SConscript("espidf.py")

FRAMEWORK_SDK_DIR = path_cache.sdk_dir
IS_INTEGRATION_DUMP = env.IsIntegrationDump()

def is_framework_subfolder(potential_subfolder):
    if not isabs(potential_subfolder):
        return False
    if splitdrive(FRAMEWORK_SDK_DIR)[0] != splitdrive(potential_subfolder)[0]:
        return False
    return commonpath([FRAMEWORK_SDK_DIR]) == commonpath([FRAMEWORK_SDK_DIR, potential_subfolder])

def shorthen_includes(env, node):
    if IS_INTEGRATION_DUMP:
        # Don't shorten include paths for IDE integrations
        return node

    # Local references for better performance
    env_get = env.get
    to_unix_path = fs.to_unix_path
    
    includes = [to_unix_path(inc) for inc in env_get("CPPPATH", [])]
    shortened_includes = []
    generic_includes = []
    
    for inc in includes:
        if is_framework_subfolder(inc):
            shortened_includes.append(
                "-iwithprefix/" + to_unix_path(relpath(inc, FRAMEWORK_SDK_DIR))
            )
        else:
            generic_includes.append(inc)

    common_flags = ["-iprefix", FRAMEWORK_SDK_DIR] + shortened_includes
    
    return env.Object(
        node,
        CPPPATH=generic_includes,
        CCFLAGS=env["CCFLAGS"] + common_flags,
        ASFLAGS=env["ASFLAGS"] + common_flags,
    )

def get_frameworks_in_current_env():
    """Determines the frameworks of the current environment"""
    if "framework" in config.options(current_env_section):
        return config.get(current_env_section, "framework", "")
    return []

# Framework check
current_env_frameworks = get_frameworks_in_current_env()
if "arduino" in current_env_frameworks and "espidf" in current_env_frameworks:
    # Arduino as component is set, switch off Hybrid compile
    flag_custom_sdkconfig = False

# Framework reinstallation if required
if check_reinstall_frwrk():
    envs = [section.replace("env:", "") for section in config.sections() if section.startswith("env:")]
    for env_name in envs:
        file_path = join(project_dir, f"sdkconfig.{env_name}")
        if exists(file_path):
            os.remove(file_path)
    
    print("*** Reinstall Arduino framework ***")
    shutil.rmtree(FRAMEWORK_DIR)
    
    arduino_frmwrk_url = str(platform.get_package_spec("framework-arduinoespressif32")).split("uri=", 1)[1][:-1]
    pm.install(arduino_frmwrk_url)
    
    if flag_custom_sdkconfig:
        call_compile_libs()
        flag_custom_sdkconfig = False

if flag_custom_sdkconfig and not flag_any_custom_sdkconfig:
    call_compile_libs()

# Main logic for Arduino Framework
pioframework = env.subst("$PIOFRAMEWORK")
arduino_lib_compile_flag = env.subst("$ARDUINO_LIB_COMPILE_FLAG")

if ("arduino" in pioframework and "espidf" not in pioframework and 
    arduino_lib_compile_flag in ("Inactive", "True")):
    
    if IS_WINDOWS:
        env.AddBuildMiddleware(shorthen_includes)
    
    # Determine build script
    pio_build = "platformio-build.py"
    build_script_path = join(FRAMEWORK_DIR, "tools", pio_build)
    
    if not exists(build_script_path):
        pio_build = "pioarduino-build.py"
        build_script_path = join(FRAMEWORK_DIR, "tools", pio_build)
    
    SConscript(build_script_path)

