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
Espressif IDF

Espressif IoT Development Framework for ESP32 MCU

https://github.com/espressif/esp-idf
"""

from SCons.Script import DefaultEnvironment, SConscript
import copy
import json
import subprocess
import sys
import shutil
import os
from os.path import join
import re
import platform as sys_platform

import click
import semantic_version

from SCons.Script import (
    ARGUMENTS,
    COMMAND_LINE_TARGETS,
    DefaultEnvironment,
)

from platformio import fs, __version__
from platformio.compat import IS_WINDOWS
from platformio.proc import exec_command
from platformio.builder.tools.piolib import ProjectAsLibBuilder
from platformio.package.version import get_original_version, pepver_to_semver

# Added to avoid conflicts between installed Python packages from
# the IDF virtual environment and PlatformIO Core
# Note: This workaround can be safely deleted when PlatformIO 6.1.7 is released
if os.environ.get("PYTHONPATH"):
    del os.environ["PYTHONPATH"]

env = DefaultEnvironment()

platform = env.PioPlatform()

IDF5 = (
    platform.get_package_version("framework-espidf")
    .split(".")[1]
    .startswith("5")
)
IDF_ENV_VERSION = "1.0.0"
FRAMEWORK_DIR = platform.get_package_dir("framework-espidf")

env = DefaultEnvironment()

def install_python_deps():
    def _get_installed_pip_packages(python_exe_path):
        result = {}
        packages = {}
        pip_output = subprocess.check_output(
            [
                python_exe_path,
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

    skip_python_packages = os.path.join(FRAMEWORK_DIR, ".pio_skip_pypackages")
    if os.path.isfile(skip_python_packages):
        return

    deps = {
        "PyYAML": ">=6.0.2",
        "wheel": ">=0.35.1",
        # https://github.com/platformio/platformio-core/issues/4614
        "urllib3": "<2",
        # https://github.com/platformio/platform-espressif32/issues/635
        "cryptography": "~=41.0.1" if IDF5 else ">=2.1.4,<35.0.0",
        "future": ">=0.18.3",
        "pyparsing": ">=3.1.0,<4" if IDF5 else ">=2.0.3,<2.4.0",
        "kconfiglib": "~=14.1.0" if IDF5 else "~=13.7.1",
        "idf-component-manager": "~=2.0.1" if IDF5 else "~=1.0",
        "esp-idf-kconfig": ">=1.4.2,<2.0.0"
    }

    if sys_platform.system() == "Darwin" and "arm" in sys_platform.machine().lower():
        deps["chardet"] = ">=3.0.2,<4"

    python_exe_path = get_python_exe()
    installed_packages = _get_installed_pip_packages(python_exe_path)
    packages_to_install = []
    for package, spec in deps.items():
        if package not in installed_packages:
            packages_to_install.append(package)
        elif spec:
            version_spec = semantic_version.Spec(spec)
            if not version_spec.match(installed_packages[package]):
                packages_to_install.append(package)

    if packages_to_install:
        env.Execute(
            env.VerboseAction(
                (
                    '"%s" -m pip install -U ' % python_exe_path
                    + " ".join(['"%s%s"' % (p, deps[p]) for p in packages_to_install])
                ),
                "Installing ESP-IDF's Python dependencies",
            )
        )

    if IS_WINDOWS and "windows-curses" not in installed_packages:
        env.Execute(
            env.VerboseAction(
                '"%s" -m pip install windows-curses' % python_exe_path,
                "Installing windows-curses package",
            )
        )

def get_framework_version():
    def _extract_from_cmake_version_file():
        version_cmake_file = os.path.join(
            FRAMEWORK_DIR, "tools", "cmake", "version.cmake"
        )
        if not os.path.isfile(version_cmake_file):
            return

        with open(version_cmake_file, encoding="utf8") as fp:
            pattern = r"set\(IDF_VERSION_(MAJOR|MINOR|PATCH) (\d+)\)"
            matches = re.findall(pattern, fp.read())
            if len(matches) != 3:
                return
            # If found all three parts of the version
            return ".".join([match[1] for match in matches])

    pkg = platform.get_package("framework-espidf")
    version = get_original_version(str(pkg.metadata.version.truncate()))
    if not version:
        # Fallback value extracted directly from the cmake version file
        version = _extract_from_cmake_version_file()
        if not version:
            version = "0.0.0"

    return version


def get_idf_venv_dir():
    # The name of the IDF venv contains the IDF version to avoid possible conflicts and
    # unnecessary reinstallation of Python dependencies in cases when Arduino
    # as an IDF component requires a different version of the IDF package and
    # hence a different set of Python deps or their versions
    idf_version = get_framework_version()
    return os.path.join(
        env.subst("$PROJECT_CORE_DIR"), "penv", ".espidf-" + idf_version
    )


def ensure_python_venv_available():

    def _is_venv_outdated(venv_data_file):
        try:
            with open(venv_data_file, "r", encoding="utf8") as fp:
                venv_data = json.load(fp)
                if venv_data.get("version", "") != IDF_ENV_VERSION:
                    return True
                return False
        except:
            return True

    def _create_venv(venv_dir):
        pip_path = os.path.join(
            venv_dir,
            "Scripts" if IS_WINDOWS else "bin",
            "pip" + (".exe" if IS_WINDOWS else ""),
        )

        if os.path.isdir(venv_dir):
            try:
                print("Removing an oudated IDF virtual environment")
                shutil.rmtree(venv_dir)
            except OSError:
                print(
                    "Error: Cannot remove an outdated IDF virtual environment. " \
                    "Please remove the `%s` folder manually!" % venv_dir
                )
                env.Exit(1)

        # Use the built-in PlatformIO Python to create a standalone IDF virtual env
        env.Execute(
            env.VerboseAction(
                '"$PYTHONEXE" -m venv --clear "%s"' % venv_dir,
                "Creating a new virtual environment for IDF Python dependencies",
            )
        )

        assert os.path.isfile(
            pip_path
        ), "Error: Failed to create a proper virtual environment. Missing the `pip` binary!"

    venv_dir = get_idf_venv_dir()
    venv_data_file = os.path.join(venv_dir, "pio-idf-venv.json")
    if not os.path.isfile(venv_data_file) or _is_venv_outdated(venv_data_file):
        _create_venv(venv_dir)
        with open(venv_data_file, "w", encoding="utf8") as fp:
            venv_info = {"version": IDF_ENV_VERSION}
            json.dump(venv_info, fp, indent=2)


def get_python_exe():
    python_exe_path = os.path.join(
        get_idf_venv_dir(),
        "Scripts" if IS_WINDOWS else "bin",
        "python" + (".exe" if IS_WINDOWS else ""),
    )

    assert os.path.isfile(python_exe_path), (
        "Error: Missing Python executable file `%s`" % python_exe_path
    )

    return python_exe_path


#
# ESP-IDF requires Python packages with specific versions in a virtual environment
#

ensure_python_venv_available()
install_python_deps()

if "espidf" in env.subst("$PIOFRAMEWORK"):
    SConscript("espidf.py")
