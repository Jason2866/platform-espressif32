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

import os
from os.path import join
import shutil

from SCons.Script import DefaultEnvironment, SConscript

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
build_core = board.get("build.core", "").lower()

SConscript("_embed_files.py", exports="env")

if "espidf" not in env.subst("$PIOFRAMEWORK"):
    SConscript(
        join(DefaultEnvironment().PioPlatform().get_package_dir(
            "framework-arduinoespressif32"), "tools", "platformio-build.py"))
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
    NIMBLE_DIR = "".join(platform.get_package_dir("esp-nimble-cpp"))
    FRAMEWORK_LIBRARY_DIR = join(FRAMEWORK_DIR, "libraries")
    TARGET_NIMBLE_DIR = join(FRAMEWORK_LIBRARY_DIR, "esp-nimble-cpp")
    print("Framework Lib Dir: ", FRAMEWORK_LIBRARY_DIR)
    print("Target Dir: ", TARGET_NIMBLE_DIR)
    if os.path.exists(FRAMEWORK_LIBRARY_DIR):
        if not os.path.exists(TARGET_NIMBLE_DIR):
            shutil.copytree(NIMBLE_DIR, FRAMEWORK_LIBRARY_DIR)
