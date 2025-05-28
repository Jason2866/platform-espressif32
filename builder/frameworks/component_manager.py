# component_manager.py
import os
import shutil
import json
import re
import yaml
from yaml import SafeLoader
from os.path import join
from typing import Set, Optional, Dict, Any, List

from SCons.Script import (
    ARGUMENTS,
    COMMAND_LINE_TARGETS,
    DefaultEnvironment,
)

from platformio.project.config import ProjectConfig


class ComponentManager:
    """Manages IDF components for ESP32 Arduino framework builds."""
    
    def __init__(self, env):
        self.env = env
        self.platform = env.PioPlatform()
        self.config = env.GetProjectConfig()
        self.board = env.BoardConfig()
        self.mcu = self.board.get("build.mcu", "esp32").lower()
        self.project_src_dir = env.subst("$PROJECT_SRC_DIR")
        self.removed_components: Set[str] = set()
        self.ignored_libs: Set[str] = set()
        
        self.arduino_framework_dir = self.platform.get_package_dir("framework-arduinoespressif32")
        self.arduino_libs_mcu = join(self.arduino_framework_dir, "tools", "esp32-arduino-libs", self.mcu)
    
    def handle_component_settings(self, add_components: bool = False, remove_components: bool = False) -> None:
        """Handle adding and removing IDF components based on project configuration."""
        if not (add_components or remove_components):
            return
        
        print("*** \"custom_component\" is used to (de)select managed idf components ***")
        
        # Create backup before first component removal
        if remove_components and not self.removed_components:
            self._backup_pioarduino_build_py()
        
        component_yml_path = self._get_or_create_component_yml()
        component_data = self._load_component_yml(component_yml_path)
        
        if remove_components:
            components_to_remove = self.env.GetProjectOption("custom_component_remove").splitlines()
            self._remove_components(component_data, components_to_remove)
        
        if add_components:
            components_to_add = self.env.GetProjectOption("custom_component_add").splitlines()
            self._add_components(component_data, components_to_add)
        
        self._save_component_yml(component_yml_path, component_data)
        
        # Clean up removed components
        if self.removed_components:
            self._cleanup_removed_components()
    
    def handle_lib_ignore(self) -> None:
        """Handle lib_ignore entries from platformio.ini and remove corresponding includes."""
        print("*** Processing lib_ignore entries from platformio.ini ***")
        
        # Create backup before processing lib_ignore
        if not self.ignored_libs:
            self._backup_pioarduino_build_py()
        
        # Get lib_ignore entries from platformio.ini
        lib_ignore_entries = self._get_lib_ignore_entries()
        
        if lib_ignore_entries:
            self.ignored_libs.update(lib_ignore_entries)
            self._remove_ignored_lib_includes()
    
    def _get_lib_ignore_entries(self) -> List[str]:
        """Get lib_ignore entries from platformio.ini configuration."""
        try:
            # Try to get lib_ignore from current environment
            lib_ignore = self.env.GetProjectOption("lib_ignore", [])
            if isinstance(lib_ignore, str):
                lib_ignore = [lib_ignore]
            
            # Also check global lib_ignore
            if hasattr(self.config, 'get'):
                global_lib_ignore = self.config.get("platformio", "lib_ignore", fallback="")
                if global_lib_ignore:
                    if isinstance(global_lib_ignore, str):
                        global_lib_ignore = global_lib_ignore.split()
                    lib_ignore.extend(global_lib_ignore)
            
            # Clean and normalize entries
            cleaned_entries = []
            for entry in lib_ignore:
                entry = entry.strip()
                if entry:
                    # Convert library names to potential include directory names
                    include_name = self._convert_lib_name_to_include(entry)
                    cleaned_entries.append(include_name)
                    print(f"*** Found lib_ignore entry: {entry} -> {include_name}")
            
            return cleaned_entries
            
        except Exception as e:
            print(f"*** Warning: Could not read lib_ignore entries: {e}")
            return []
    
    def _convert_lib_name_to_include(self, lib_name: str) -> str:
        """Convert library name to potential include directory name."""
        # Remove common prefixes and suffixes
        lib_name = lib_name.lower()
        
        # Remove common prefixes
        prefixes_to_remove = ['lib', 'arduino-', 'esp32-', 'esp-']
        for prefix in prefixes_to_remove:
            if lib_name.startswith(prefix):
                lib_name = lib_name[len(prefix):]
        
        # Remove common suffixes
        suffixes_to_remove = ['-lib', '-library', '.h']
        for suffix in suffixes_to_remove:
            if lib_name.endswith(suffix):
                lib_name = lib_name[:-len(suffix)]
        
        # Convert common library names to their include directory equivalents
        lib_mapping = {
            'wifi': 'esp_wifi',
            'bluetooth': 'bt',
            'ble': 'bt',
            'bt': 'bt',
            'ethernet': 'esp_eth',
            'websocket': 'esp_websocket_client',
            'http': 'esp_http_client',
            'https': 'esp_https_ota',
            'ota': 'esp_https_ota',
            'spiffs': 'spiffs',
            'fatfs': 'fatfs',
            'nvs': 'nvs_flash',
            'mesh': 'esp_wifi_mesh',
            'smartconfig': 'esp_smartconfig',
            'mdns': 'mdns',
            'coap': 'coap',
            'mqtt': 'mqtt',
            'json': 'cjson',
            'mbedtls': 'mbedtls',
            'openssl': 'openssl'
        }
        
        return lib_mapping.get(lib_name, lib_name)
    
    def _remove_ignored_lib_includes(self) -> None:
        """Remove include entries for ignored libraries from pioarduino-build.py."""
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        
        if not os.path.exists(build_py_path):
            print(f"*** Warning: pioarduino-build.py not found at {build_py_path}")
            return
        
        with open(build_py_path, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Remove CPPPATH entries for each ignored library
        for lib_name in self.ignored_libs:
            # Multiple patterns to catch different include formats
            patterns = [
                # Pattern für: join(..., "include", "lib_name", ...)
                rf'.*join\([^,]*,\s*"include",\s*"{re.escape(lib_name)}"[^)]*\),?\n',
                # Pattern für direkte String-Matches
                rf'.*"include/{re.escape(lib_name)}"[^,\n]*,?\n',
                # Pattern für Listen-Einträge mit include/lib_name
                rf'.*"[^"]*include[^"]*{re.escape(lib_name)}[^"]*"[^,\n]*,?\n',
                # Pattern für absolute Pfade
                rf'.*"[^"]*/{re.escape(lib_name)}/include[^"]*"[^,\n]*,?\n',
                # Pattern für Pfade die lib_name enthalten
                rf'.*"[^"]*{re.escape(lib_name)}[^"]*include[^"]*"[^,\n]*,?\n'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, '', content)
                    print(f"*** Removed include entries for ignored library: {lib_name} ({len(matches)} entries)")
        
        # Clean up empty lines and trailing commas
        content = re.sub(r'\n\s*\n', '\n', content)  # Remove multiple empty lines
        content = re.sub(r',\s*\n\s*\]', '\n]', content)  # Fix trailing commas before closing brackets
        
        # Only write if content changed
        if content != original_content:
            with open(build_py_path, 'w') as f:
                f.write(content)
            print(f"*** Updated pioarduino-build.py to remove {len(self.ignored_libs)} ignored library includes")
        else:
            print("*** No matching include entries found for ignored libraries")
    
    def _get_or_create_component_yml(self) -> str:
        """Get path to idf_component.yml, creating it if necessary."""
        # Try Arduino framework first
        framework_yml = join(self.arduino_framework_dir, "idf_component.yml")
        if os.path.exists(framework_yml):
            self._create_backup(framework_yml)
            return framework_yml
        
        # Try project source directory
        project_yml = join(self.project_src_dir, "idf_component.yml")
        if os.path.exists(project_yml):
            self._create_backup(project_yml)
            return project_yml
        
        # Create new file in project source
        self._create_default_component_yml(project_yml)
        return project_yml
    
    def _create_backup(self, file_path: str) -> None:
        """Create backup of a file."""
        backup_path = f"{file_path}.orig"
        if not os.path.exists(backup_path):
            shutil.copy(file_path, backup_path)
    
    def _create_default_component_yml(self, file_path: str) -> None:
        """Create a default idf_component.yml file."""
        default_content = {
            "dependencies": {
                "idf": ">=5.1"
            }
        }
        
        with open(file_path, 'w') as f:
            yaml.dump(default_content, f)
    
    def _load_component_yml(self, file_path: str) -> Dict[str, Any]:
        """Load and parse idf_component.yml file."""
        with open(file_path, "r") as f:
            return yaml.load(f, Loader=SafeLoader) or {"dependencies": {}}
    
    def _save_component_yml(self, file_path: str, data: Dict[str, Any]) -> None:
        """Save component data to YAML file."""
        with open(file_path, "w") as f:
            yaml.dump(data, f)
    
    def _remove_components(self, component_data: Dict[str, Any], components_to_remove: list) -> None:
        """Remove specified components from the configuration."""
        dependencies = component_data.setdefault("dependencies", {})
        
        for component in components_to_remove:
            component = component.strip()
            if not component:
                continue
                
            if component in dependencies:
                print(f"*** Removing component: {component}")
                del dependencies[component]
                
                # Track for cleanup
                filesystem_name = self._convert_component_name_to_filesystem(component)
                self.removed_components.add(filesystem_name)
    
    def _add_components(self, component_data: Dict[str, Any], components_to_add: list) -> None:
        """Add specified components to the configuration."""
        dependencies = component_data.setdefault("dependencies", {})
        
        for component in components_to_add:
            component = component.strip()
            if len(component) <= 4:  # Skip too short entries
                continue
            
            component_name, version = self._parse_component_entry(component)
            
            if component_name not in dependencies:
                print(f"*** Adding component: {component_name} {version}")
                dependencies[component_name] = {"version": version}
    
    def _parse_component_entry(self, entry: str) -> tuple[str, str]:
        """Parse component entry into name and version."""
        if "@" in entry:
            name, version = entry.split("@", 1)
            return name.strip(), version.strip()
        return entry.strip(), "*"
    
    def _convert_component_name_to_filesystem(self, component_name: str) -> str:
        """Convert component name from registry format to filesystem format."""
        return component_name.replace("/", "__")
    
    def _backup_pioarduino_build_py(self) -> None:
        """Create backup of the original pioarduino-build.py."""
        if "arduino" not in self.env.subst("$PIOFRAMEWORK"):
            return
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        backup_path = join(self.arduino_libs_mcu, f"pioarduino-build.py.{self.mcu}")
        
        if os.path.exists(build_py_path) and not os.path.exists(backup_path):
            shutil.copy2(build_py_path, backup_path)
            print(f"*** Created backup of pioarduino-build.py for: {self.mcu}")
    
    def _cleanup_removed_components(self) -> None:
        """Clean up removed components and restore original build file."""
        for component in self.removed_components:
            self._remove_include_directory(component)
        
        self._remove_cpppath_entries()
    
    def _remove_include_directory(self, component: str) -> None:
        """Remove include directory for a component."""
        include_path = join(self.arduino_libs_mcu, "include", component)
        if os.path.exists(include_path):
            shutil.rmtree(include_path)
            print(f"*** Removed include directory: {component}")
    
    def _remove_cpppath_entries(self) -> None:
        """Remove CPPPATH entries for removed components from pioarduino-build.py."""
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        
        if not os.path.exists(build_py_path):
            return
        
        with open(build_py_path, 'r') as f:
            content = f.read()
        
        # Remove CPPPATH entries for each removed component
        for component in self.removed_components:
            # Pattern für: join(..., "include", "component_name", ...)
            pattern1 = rf'.*join\([^,]*,\s*"include",\s*"{re.escape(component)}"[^)]*\),?\n'
            content = re.sub(pattern1, '', content)
            
            # Pattern für: join(..., "include", "bt") oder ähnliche feste Strings
            pattern2 = rf'.*join\([^,]*,\s*"include",\s*"{re.escape(component)}"[^)]*\),?\n'
            content = re.sub(pattern2, '', content)
            
            # Zusätzliches Pattern für direkte String-Matches ohne join()
            pattern3 = rf'.*"include/{re.escape(component)}"[^,\n]*,?\n'
            content = re.sub(pattern3, '', content)
            
            # Pattern für Listen-Einträge mit include/component
            pattern4 = rf'.*"[^"]*include[^"]*{re.escape(component)}[^"]*"[^,\n]*,?\n'
            content = re.sub(pattern4, '', content)
            
            print(f"*** Removed CPPPATH entry for: {component}")
        
        with open(build_py_path, 'w') as f:
            f.write(content)
    
    def restore_pioarduino_build_py(self, source=None, target=None, env=None) -> None:
        """Restore the original pioarduino-build.py from backup."""
        if "arduino" not in self.env.subst("$PIOFRAMEWORK"):
            return
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        backup_path = join(self.arduino_libs_mcu, f"pioarduino-build.py.{self.mcu}")
        
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, build_py_path)
            os.remove(backup_path)
            print(f"*** Restored original pioarduino-build.py for: {self.mcu}")


# Legacy function wrappers for backward compatibility
env = DefaultEnvironment()
_component_manager = ComponentManager(env)

def HandleCOMPONENTsettings(env, flag_custom_component_add, flag_custom_component_remove):
    """Legacy wrapper function for backward compatibility."""
    _component_manager.handle_component_settings(
        add_components=flag_custom_component_add,
        remove_components=flag_custom_component_remove
    )

def HandleLIBIGNORE(env):
    """Handle lib_ignore entries from platformio.ini."""
    _component_manager.handle_lib_ignore()

def restore_pioarduino_build_py(source, target, env):
    """Legacy wrapper function for backward compatibility."""
    _component_manager.restore_pioarduino_build_py(source, target, env)

# Export global variables for backward compatibility
removed_components = _component_manager.removed_components
ignored_libs = _component_manager.ignored_libs
