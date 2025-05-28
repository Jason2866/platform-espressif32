# component_manager.py
import os
import shutil
import re
import yaml
from yaml import SafeLoader
from os.path import join
from typing import Set, Optional, Dict, Any, List


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
        
        print(f"*** ComponentManager initialized for MCU: {self.mcu}")
        print(f"*** Arduino Framework Dir: {self.arduino_framework_dir}")
        print(f"*** Arduino Libs MCU Dir: {self.arduino_libs_mcu}")
    
    def handle_component_settings(self, add_components: bool = False, remove_components: bool = False) -> None:
        """Handle adding and removing IDF components based on project configuration."""
        print(f"*** handle_component_settings called: add={add_components}, remove={remove_components}")
        
        if not (add_components or remove_components):
            print("*** No component operations requested, skipping")
            return
        
        # Create backup before first component removal
        if remove_components and not self.removed_components:
            print("*** Creating backup before component removal")
            self._backup_pioarduino_build_py()
        
        component_yml_path = self._get_or_create_component_yml()
        print(f"*** Using component.yml at: {component_yml_path}")
        
        component_data = self._load_component_yml(component_yml_path)
        print(f"*** Loaded component data: {component_data}")
        
        if remove_components:
            try:
                components_to_remove = self.env.GetProjectOption("custom_component_remove").splitlines()
                print(f"*** Components to remove: {components_to_remove}")
                self._remove_components(component_data, components_to_remove)
            except:
                pass
        
        if add_components:
            try:
                components_to_add = self.env.GetProjectOption("custom_component_add").splitlines()
                print(f"*** Components to add: {components_to_add}")
                self._add_components(component_data, components_to_add)
            except:
                pass
        
        self._save_component_yml(component_yml_path, component_data)
        print("*** Component YAML saved")
        
        # Clean up removed components
        if self.removed_components:
            print(f"*** Cleaning up {len(self.removed_components)} removed components")
            self._cleanup_removed_components()
    
    def handle_lib_ignore(self) -> None:
        """Handle lib_ignore entries from platformio.ini and remove corresponding includes."""
        print("*** Processing lib_ignore entries from platformio.ini ***")
        
        # Create backup before processing lib_ignore
        if not self.ignored_libs:
            print("*** Creating backup before lib_ignore processing")
            self._backup_pioarduino_build_py()
        
        # Get lib_ignore entries from current environment only
        lib_ignore_entries = self._get_lib_ignore_entries()
        print(f"*** Found {len(lib_ignore_entries)} lib_ignore entries: {lib_ignore_entries}")
        
        if lib_ignore_entries:
            self.ignored_libs.update(lib_ignore_entries)
            print(f"*** Total ignored libs: {list(self.ignored_libs)}")
            self._remove_ignored_lib_includes()
        else:
            print("*** No lib_ignore entries found to process")
    
    def _get_lib_ignore_entries(self) -> List[str]:
        """Get lib_ignore entries from current environment configuration only."""
        print("*** Reading lib_ignore entries from current environment")
        
        try:
            # Get lib_ignore from current environment only
            lib_ignore = self.env.GetProjectOption("lib_ignore", [])
            print(f"*** Environment lib_ignore: {lib_ignore} (type: {type(lib_ignore)})")
            
            if isinstance(lib_ignore, str):
                lib_ignore = [lib_ignore]
            elif lib_ignore is None:
                lib_ignore = []
            
            # Clean and normalize entries
            cleaned_entries = []
            for entry in lib_ignore:
                entry = str(entry).strip()
                if entry:
                    # Convert library names to potential include directory names
                    include_name = self._convert_lib_name_to_include(entry)
                    cleaned_entries.append(include_name)
                    print(f"*** Mapped lib_ignore entry: '{entry}' -> '{include_name}'")
            
            print(f"*** Final cleaned entries: {cleaned_entries}")
            return cleaned_entries
            
        except Exception as e:
            print(f"*** Error reading lib_ignore entries: {e}")
            import traceback
            print(f"*** Traceback: {traceback.format_exc()}")
            return []
    
    def _get_arduino_core_libraries(self) -> Dict[str, str]:
        """Get all Arduino core libraries and their corresponding include paths."""
        print("*** Scanning Arduino core libraries")
        libraries_mapping = {}
        
        # Path to Arduino Core Libraries
        arduino_libs_dir = join(self.arduino_framework_dir, "libraries")
        
        if not os.path.exists(arduino_libs_dir):
            print(f"*** Warning: Arduino libraries directory not found: {arduino_libs_dir}")
            return libraries_mapping
        
        print(f"*** Scanning Arduino core libraries in: {arduino_libs_dir}")
        
        try:
            for entry in os.listdir(arduino_libs_dir):
                lib_path = join(arduino_libs_dir, entry)
                if os.path.isdir(lib_path):
                    lib_name = self._get_library_name_from_properties(lib_path)
                    if lib_name:
                        include_path = self._map_library_to_include_path(lib_name, entry)
                        libraries_mapping[lib_name.lower()] = include_path
                        libraries_mapping[entry.lower()] = include_path  # Also use directory name as key
                        print(f"*** Found library: {lib_name} ({entry}) -> {include_path}")
                    else:
                        print(f"*** No library.properties found for: {entry}")
        except Exception as e:
            print(f"*** Error scanning Arduino libraries: {e}")
        
        print(f"*** Total libraries mapped: {len(libraries_mapping)}")
        return libraries_mapping
    
    def _get_library_name_from_properties(self, lib_dir: str) -> Optional[str]:
        """Extract library name from library.properties file."""
        prop_path = join(lib_dir, "library.properties")
        if not os.path.isfile(prop_path):
            return None
        
        try:
            with open(prop_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('name='):
                        name = line.split('=', 1)[1].strip()
                        print(f"*** Library name from properties: {name}")
                        return name
        except Exception as e:
            print(f"*** Warning: Could not read {prop_path}: {e}")
        
        return None
    
    def _map_library_to_include_path(self, lib_name: str, dir_name: str) -> str:
        """Map library name to corresponding include path."""
        lib_name_lower = lib_name.lower().replace(' ', '').replace('-', '_')
        dir_name_lower = dir_name.lower()
        
        print(f"*** Mapping library: '{lib_name}' (dir: '{dir_name}') -> normalized: '{lib_name_lower}'")
        
        # Extended mapping list with Arduino Core Libraries
        extended_mapping = {
            # Core ESP32 mappings
            'wifi': 'esp_wifi',
            'bluetooth': 'bt',
            'bluetoothserial': 'bt',
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
            'openssl': 'openssl',
            
            # Arduino Core specific mappings
            'esp32blearduino': 'bt',
            'esp32_ble_arduino': 'bt',
            'esp32': 'esp32',
            'wire': 'driver',
            'spi': 'driver',
            'i2c': 'driver',
            'uart': 'driver',
            'serial': 'driver',
            'analogwrite': 'driver',
            'ledc': 'driver',
            'pwm': 'driver',
            'dac': 'driver',
            'adc': 'driver',
            'touch': 'driver',
            'hall': 'driver',
            'rtc': 'driver',
            'timer': 'esp_timer',
            'preferences': 'nvs_flash',
            'eeprom': 'nvs_flash',
            'update': 'esp_https_ota',
            'httpupdate': 'esp_https_ota',
            'httpclient': 'esp_http_client',
            'httpsclient': 'esp_https_ota',
            'wifimanager': 'esp_wifi',
            'wificlientsecure': 'esp_wifi',
            'wifiserver': 'esp_wifi',
            'wifiudp': 'esp_wifi',
            'wificlient': 'esp_wifi',
            'wifiap': 'esp_wifi',
            'wifimulti': 'esp_wifi',
            'esp32webserver': 'esp_http_server',
            'webserver': 'esp_http_server',
            'asyncwebserver': 'esp_http_server',
            'dnsserver': 'lwip',
            'netbios': 'netbios',
            'simpletime': 'lwip',
            'fs': 'vfs',
            'sd': 'fatfs',
            'sd_mmc': 'fatfs',
            'littlefs': 'esp_littlefs',
            'ffat': 'fatfs',
            'camera': 'esp32_camera',
            'esp_camera': 'esp32_camera',
            'arducam': 'esp32_camera',
            'rainmaker': 'esp_rainmaker',
            'esp_rainmaker': 'esp_rainmaker',
            'provisioning': 'wifi_provisioning',
            'wifiprovisioning': 'wifi_provisioning',
            'espnow': 'esp_now',
            'esp_now': 'esp_now',
            'esptouch': 'esp_smartconfig',
            'smartconfig': 'esp_smartconfig',
            'ping': 'lwip',
            'netif': 'lwip',
            'tcpip': 'lwip',
            'lwip': 'lwip',
            'freertos': 'freertos',
            'rtos': 'freertos',
            'task': 'freertos',
            'queue': 'freertos',
            'semaphore': 'freertos',
            'mutex': 'freertos',
            'eventgroup': 'freertos',
            'streambuffer': 'freertos',
            'messagebuffer': 'freertos'
        }
        
        # Check extended mapping first
        if lib_name_lower in extended_mapping:
            mapped_path = extended_mapping[lib_name_lower]
            print(f"*** Found mapping: '{lib_name_lower}' -> '{mapped_path}'")
            return mapped_path
        
        # Check directory name
        if dir_name_lower in extended_mapping:
            mapped_path = extended_mapping[dir_name_lower]
            print(f"*** Found mapping by dir name: '{dir_name_lower}' -> '{mapped_path}'")
            return mapped_path
        
        # Fallback: Use directory name as include path
        print(f"*** No mapping found, using directory name: '{dir_name_lower}'")
        return dir_name_lower
    
    def _convert_lib_name_to_include(self, lib_name: str) -> str:
        """Convert library name to potential include directory name."""
        print(f"*** Converting lib name to include: '{lib_name}'")
        
        # Load Arduino Core Libraries on first call
        if not hasattr(self, '_arduino_libraries_cache'):
            print("*** Loading Arduino libraries cache")
            self._arduino_libraries_cache = self._get_arduino_core_libraries()
        
        lib_name_lower = lib_name.lower()
        
        # Check Arduino Core Libraries first
        if lib_name_lower in self._arduino_libraries_cache:
            result = self._arduino_libraries_cache[lib_name_lower]
            print(f"*** Found in Arduino libraries cache: '{lib_name}' -> '{result}'")
            return result
        
        # Fallback to original logic
        # Remove common prefixes and suffixes
        cleaned_name = lib_name_lower
        print(f"*** Cleaning lib name: '{cleaned_name}'")
        
        # Remove common prefixes
        prefixes_to_remove = ['lib', 'arduino-', 'esp32-', 'esp-']
        for prefix in prefixes_to_remove:
            if cleaned_name.startswith(prefix):
                old_name = cleaned_name
                cleaned_name = cleaned_name[len(prefix):]
                print(f"*** Removed prefix '{prefix}': '{old_name}' -> '{cleaned_name}'")
        
        # Remove common suffixes
        suffixes_to_remove = ['-lib', '-library', '.h']
        for suffix in suffixes_to_remove:
            if cleaned_name.endswith(suffix):
                old_name = cleaned_name
                cleaned_name = cleaned_name[:-len(suffix)]
                print(f"*** Removed suffix '{suffix}': '{old_name}' -> '{cleaned_name}'")
        
        # Check again with cleaned name
        if cleaned_name in self._arduino_libraries_cache:
            result = self._arduino_libraries_cache[cleaned_name]
            print(f"*** Found cleaned name in cache: '{cleaned_name}' -> '{result}'")
            return result
        
        # Direct mapping for common cases not in Arduino libraries
        direct_mapping = {
            'ble': 'bt',
            'bluetooth': 'bt',
            'bluetoothserial': 'bt'
        }
        
        if cleaned_name in direct_mapping:
            result = direct_mapping[cleaned_name]
            print(f"*** Found in direct mapping: '{cleaned_name}' -> '{result}'")
            return result
        
        print(f"*** Final conversion result: '{lib_name}' -> '{cleaned_name}'")
        return cleaned_name
    
    def _remove_ignored_lib_includes(self) -> None:
        """Remove include entries for ignored libraries from pioarduino-build.py."""
        print(f"*** Removing include entries for {len(self.ignored_libs)} ignored libraries")
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        print(f"*** Target file: {build_py_path}")
        
        if not os.path.exists(build_py_path):
            print(f"*** Error: pioarduino-build.py not found at {build_py_path}")
            return
        
        try:
            with open(build_py_path, 'r') as f:
                content = f.read()
            
            original_content = content
            original_lines = len(content.splitlines())
            print(f"*** Original file has {original_lines} lines")
            
            total_removed = 0
            
            # Remove CPPPATH entries for each ignored library
            for lib_name in self.ignored_libs:
                print(f"*** Processing ignored library: '{lib_name}'")
                
                # Multiple patterns to catch different include formats
                patterns = [
                    # Pattern for: join(..., "include", "lib_name", ...)
                    rf'.*join\([^,]*,\s*"include",\s*"{re.escape(lib_name)}"[^)]*\),?\n',
                    # Pattern for direct string matches
                    rf'.*"include/{re.escape(lib_name)}"[^,\n]*,?\n',
                    # Pattern for list entries with include/lib_name
                    rf'.*"[^"]*include[^"]*{re.escape(lib_name)}[^"]*"[^,\n]*,?\n',
                    # Pattern for absolute paths
                    rf'.*"[^"]*/{re.escape(lib_name)}/include[^"]*"[^,\n]*,?\n',
                    # Pattern for paths containing lib_name
                    rf'.*"[^"]*{re.escape(lib_name)}[^"]*include[^"]*"[^,\n]*,?\n',
                    # Additional robust patterns
                    rf'.*join\([^)]*"include"[^)]*"{re.escape(lib_name)}"[^)]*\),?\n',
                    rf'.*"{re.escape(lib_name)}/include"[^,\n]*,?\n',
                    rf'\s*"[^"]*/{re.escape(lib_name)}/[^"]*",?\n'
                ]
                
                lib_removed_count = 0
                for i, pattern in enumerate(patterns):
                    matches = re.findall(pattern, content)
                    if matches:
                        print(f"*** Pattern {i+1} found {len(matches)} matches for '{lib_name}':")
                        for match in matches:
                            print(f"***   - {match.strip()}")
                        content = re.sub(pattern, '', content)
                        lib_removed_count += len(matches)
                
                if lib_removed_count > 0:
                    print(f"*** Removed {lib_removed_count} include entries for '{lib_name}'")
                    total_removed += lib_removed_count
                else:
                    print(f"*** No include entries found for '{lib_name}'")
            
            # Clean up empty lines and trailing commas
            content = re.sub(r'\n\s*\n', '\n', content)  # Remove multiple empty lines
            content = re.sub(r',\s*\n\s*\]', '\n]', content)  # Fix trailing commas before closing brackets
            
            new_lines = len(content.splitlines())
            lines_removed = original_lines - new_lines
            
            print(f"*** File statistics:")
            print(f"***   Original lines: {original_lines}")
            print(f"***   New lines: {new_lines}")
            print(f"***   Lines removed: {lines_removed}")
            print(f"***   Total pattern matches: {total_removed}")
            
            # Validate changes
            if self._validate_changes(original_content, content):
                # Only write if content changed
                if content != original_content:
                    with open(build_py_path, 'w') as f:
                        f.write(content)
                    print(f"*** Successfully updated pioarduino-build.py")
                    print(f"*** Removed {total_removed} include entries for {len(self.ignored_libs)} ignored libraries")
                else:
                    print("*** No changes made to pioarduino-build.py")
            else:
                print("*** Changes validation failed, file not modified")
                
        except Exception as e:
            print(f"*** Error processing pioarduino-build.py: {e}")
            import traceback
            print(f"*** Traceback: {traceback.format_exc()}")
    
    def _validate_changes(self, original_content: str, new_content: str) -> bool:
        """Validate that the changes are reasonable."""
        original_lines = len(original_content.splitlines())
        new_lines = len(new_content.splitlines())
        removed_lines = original_lines - new_lines
        
        print(f"*** Validating changes: {removed_lines} lines removed ({removed_lines/original_lines*100:.1f}%)")
        
        if removed_lines > original_lines * 0.5:  # More than 50% removed
            print(f"*** Warning: Removed {removed_lines} lines ({removed_lines/original_lines*100:.1f}%) - seems excessive")
            return False
        
        if removed_lines < 0:
            print(f"*** Warning: File grew by {abs(removed_lines)} lines - unexpected")
            return False
        
        print("*** Changes validation passed")
        return True
    
    def _get_or_create_component_yml(self) -> str:
        """Get path to idf_component.yml, creating it if necessary."""
        print("*** Looking for idf_component.yml")
        
        # Try Arduino framework first
        framework_yml = join(self.arduino_framework_dir, "idf_component.yml")
        if os.path.exists(framework_yml):
            print(f"*** Found framework component.yml: {framework_yml}")
            self._create_backup(framework_yml)
            return framework_yml
        
        # Try project source directory
        project_yml = join(self.project_src_dir, "idf_component.yml")
        if os.path.exists(project_yml):
            print(f"*** Found project component.yml: {project_yml}")
            self._create_backup(project_yml)
            return project_yml
        
        # Create new file in project source
        print(f"*** Creating new component.yml: {project_yml}")
        self._create_default_component_yml(project_yml)
        return project_yml
    
    def _create_backup(self, file_path: str) -> None:
        """Create backup of a file."""
        backup_path = f"{file_path}.orig"
        if not os.path.exists(backup_path):
            shutil.copy(file_path, backup_path)
            print(f"*** Created backup: {backup_path}")
        else:
            print(f"*** Backup already exists: {backup_path}")
    
    def _create_default_component_yml(self, file_path: str) -> None:
        """Create a default idf_component.yml file."""
        print(f"*** Creating default component.yml at: {file_path}")
        default_content = {
            "dependencies": {
                "idf": ">=5.1"
            }
        }
        
        with open(file_path, 'w') as f:
            yaml.dump(default_content, f)
        print("*** Default component.yml created")
    
    def _load_component_yml(self, file_path: str) -> Dict[str, Any]:
        """Load and parse idf_component.yml file."""
        print(f"*** Loading component.yml from: {file_path}")
        try:
            with open(file_path, "r") as f:
                data = yaml.load(f, Loader=SafeLoader) or {"dependencies": {}}
            print(f"*** Loaded component data: {data}")
            return data
        except Exception as e:
            print(f"*** Error loading component.yml: {e}")
            return {"dependencies": {}}
    
    def _save_component_yml(self, file_path: str, data: Dict[str, Any]) -> None:
        """Save component data to YAML file."""
        print(f"*** Saving component.yml to: {file_path}")
        try:
            with open(file_path, "w") as f:
                yaml.dump(data, f)
            print("*** Component.yml saved successfully")
        except Exception as e:
            print(f"*** Error saving component.yml: {e}")
    
    def _remove_components(self, component_data: Dict[str, Any], components_to_remove: list) -> None:
        """Remove specified components from the configuration."""
        dependencies = component_data.setdefault("dependencies", {})
        print(f"*** Current dependencies: {list(dependencies.keys())}")
        
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
                print(f"*** Added to removal tracking: {filesystem_name}")
            else:
                print(f"*** Component not found in dependencies: {component}")
    
    def _add_components(self, component_data: Dict[str, Any], components_to_add: list) -> None:
        """Add specified components to the configuration."""
        dependencies = component_data.setdefault("dependencies", {})
        print(f"*** Current dependencies before adding: {list(dependencies.keys())}")
        
        for component in components_to_add:
            component = component.strip()
            if len(component) <= 4:  # Skip too short entries
                print(f"*** Skipping too short component entry: {component}")
                continue
            
            component_name, version = self._parse_component_entry(component)
            
            if component_name not in dependencies:
                print(f"*** Adding component: {component_name} {version}")
                dependencies[component_name] = {"version": version}
            else:
                print(f"*** Component already exists: {component_name}")
    
    def _parse_component_entry(self, entry: str) -> tuple[str, str]:
        """Parse component entry into name and version."""
        if "@" in entry:
            name, version = entry.split("@", 1)
            result = (name.strip(), version.strip())
        else:
            result = (entry.strip(), "*")
        
        print(f"*** Parsed component entry: '{entry}' -> {result}")
        return result
    
    def _convert_component_name_to_filesystem(self, component_name: str) -> str:
        """Convert component name from registry format to filesystem format."""
        result = component_name.replace("/", "__")
        print(f"*** Converted component name: '{component_name}' -> '{result}'")
        return result
    
    def _backup_pioarduino_build_py(self) -> None:
        """Create backup of the original pioarduino-build.py."""
        if "arduino" not in self.env.subst("$PIOFRAMEWORK"):
            print("*** Not using Arduino framework, skipping backup")
            return
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        backup_path = join(self.arduino_libs_mcu, f"pioarduino-build.py.{self.mcu}")
        
        print(f"*** Checking for backup: {backup_path}")
        
        if os.path.exists(build_py_path) and not os.path.exists(backup_path):
            shutil.copy2(build_py_path, backup_path)
            print(f"*** Created backup of pioarduino-build.py for: {self.mcu}")
        elif os.path.exists(backup_path):
            print(f"*** Backup already exists for: {self.mcu}")
        else:
            print(f"*** Warning: pioarduino-build.py not found at: {build_py_path}")
    
    def _cleanup_removed_components(self) -> None:
        """Clean up removed components and restore original build file."""
        print(f"*** Cleaning up {len(self.removed_components)} removed components")
        
        for component in self.removed_components:
            self._remove_include_directory(component)
        
        self._remove_cpppath_entries()
    
    def _remove_include_directory(self, component: str) -> None:
        """Remove include directory for a component."""
        include_path = join(self.arduino_libs_mcu, "include", component)
        print(f"*** Checking include directory: {include_path}")
        
        if os.path.exists(include_path):
            shutil.rmtree(include_path)
            print(f"*** Removed include directory: {component}")
        else:
            print(f"*** Include directory not found: {component}")
    
    def _remove_cpppath_entries(self) -> None:
        """Remove CPPPATH entries for removed components from pioarduino-build.py."""
        print("*** Removing CPPPATH entries for removed components")
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        
        if not os.path.exists(build_py_path):
            print(f"*** pioarduino-build.py not found: {build_py_path}")
            return
        
        try:
            with open(build_py_path, 'r') as f:
                content = f.read()
            
            original_content = content
            
            # Remove CPPPATH entries for each removed component
            for component in self.removed_components:
                print(f"*** Removing CPPPATH entries for component: {component}")
                
                # Pattern for: join(..., "include", "component_name", ...)
                pattern1 = rf'.*join\([^,]*,\s*"include",\s*"{re.escape(component)}"[^)]*\),?\n'
                matches1 = re.findall(pattern1, content)
                content = re.sub(pattern1, '', content)
                
                # Additional pattern for direct string matches without join()
                pattern2 = rf'.*"include/{re.escape(component)}"[^,\n]*,?\n'
                matches2 = re.findall(pattern2, content)
                content = re.sub(pattern2, '', content)
                
                # Pattern for list entries with include/component
                pattern3 = rf'.*"[^"]*include[^"]*{re.escape(component)}[^"]*"[^,\n]*,?\n'
                matches3 = re.findall(pattern3, content)
                content = re.sub(pattern3, '', content)
                
                total_matches = len(matches1) + len(matches2) + len(matches3)
                if total_matches > 0:
                    print(f"*** Removed {total_matches} CPPPATH entries for: {component}")
                else:
                    print(f"*** No CPPPATH entries found for: {component}")
            
            if content != original_content:
                with open(build_py_path, 'w') as f:
                    f.write(content)
                print("*** CPPPATH cleanup completed")
            else:
                print("*** No CPPPATH changes needed")
                
        except Exception as e:
            print(f"*** Error during CPPPATH cleanup: {e}")
    
    def restore_pioarduino_build_py(self, source=None, target=None, env=None) -> None:
        """Restore the original pioarduino-build.py from backup."""
        print("*** Restoring original pioarduino-build.py")
        
        build_py_path = join(self.arduino_libs_mcu, "pioarduino-build.py")
        backup_path = join(self.arduino_libs_mcu, f"pioarduino-build.py.{self.mcu}")
        
        print(f"*** Looking for backup: {backup_path}")
        
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, build_py_path)
            os.remove(backup_path)
            print(f"*** Restored original pioarduino-build.py for: {self.mcu}")
        else:
            print(f"*** No backup found for: {self.mcu}")
