# component_manager.py
import os
import shutil
import json
import re
import yaml
from yaml import SafeLoader
from os.path import join
from typing import Set, Optional, Dict, Any

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
            pattern = rf'.*join\([^,]*,\s*"include",\s*"{re.escape(component)}"[^)]*\),?\n'
            content = re.sub(pattern, '', content)
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

def restore_pioarduino_build_py(source, target, env):
    """Legacy wrapper function for backward compatibility."""
    _component_manager.restore_pioarduino_build_py(source, target, env)

# Export global variables for backward compatibility
removed_components = _component_manager.removed_components
