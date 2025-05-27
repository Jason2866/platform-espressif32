# component_manager.py
import os
import shutil
import json
import re
import yaml
from yaml import SafeLoader
from os.path import join

from SCons.Script import (
    ARGUMENTS,
    COMMAND_LINE_TARGETS,
    DefaultEnvironment,
)

from platformio.project.config import ProjectConfig

env = DefaultEnvironment()
platform = env.PioPlatform()
config = env.GetProjectConfig()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32").lower()
PROJECT_SRC_DIR = env.subst("$PROJECT_SRC_DIR")

flag_custom_component_add = False
flag_custom_component_remove = False
removed_components = set()

ARDUINO_FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
arduino_libs_mcu = join(ARDUINO_FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu)


def HandleCOMPONENTsettings(env, flag_custom_component_add, flag_custom_component_remove):
    global removed_components
    
    if flag_custom_component_add == True or flag_custom_component_remove == True: # todo remove duplicated
        print("*** \"custom_component\" is used to (de)select managed idf components ***")
        
        # Create backup of pioarduino-build.py on first component removal
        if flag_custom_component_remove == True and not removed_components:
            backup_pioarduino_build_py()
        
        if flag_custom_component_remove == True:
            idf_custom_component_remove = env.GetProjectOption("custom_component_remove").splitlines()
        else:
            idf_custom_component_remove = ""
        if flag_custom_component_add == True:
            idf_custom_component_add = env.GetProjectOption("custom_component_add").splitlines()
        else:
            idf_custom_component_add = ""

        # search "idf_component.yml" file
        try: # 1.st in Arduino framework
            idf_component_yml_src = os.path.join(ARDUINO_FRAMEWORK_DIR, "idf_component.yml")
            shutil.copy(join(ARDUINO_FRAMEWORK_DIR,"idf_component.yml"),join(ARDUINO_FRAMEWORK_DIR,"idf_component.yml.orig"))
            yml_file_dir = idf_component_yml_src
        except: # 2.nd Project source
            try:
                idf_component_yml_src = os.path.join(PROJECT_SRC_DIR, "idf_component.yml")
                shutil.copy(join(PROJECT_SRC_DIR,"idf_component.yml"),join(PROJECT_SRC_DIR,"idf_component.yml.orig"))
                yml_file_dir = idf_component_yml_src
            except: # no idf_component.yml in Project source -> create
                idf_component_yml_src = os.path.join(PROJECT_SRC_DIR, "idf_component.yml")
                yml_file_dir = idf_component_yml_src
                idf_component_yml_str = """
                    dependencies:
                      idf: \">=5.1\"
                """
                idf_component_yml = yaml.safe_load(idf_component_yml_str)
                with open(idf_component_yml_src, 'w',) as f :
                    yaml.dump(idf_component_yml,f) 

        yaml_file=open(idf_component_yml_src,"r")
        idf_component=yaml.load(yaml_file, Loader=SafeLoader)
        idf_component_str=json.dumps(idf_component)      # convert to json string
        idf_component_json=json.loads(idf_component_str) # convert string to json dict

        if idf_custom_component_remove != "":
            for entry in idf_custom_component_remove:
                # checking if the entry exists before removing
                if entry in idf_component_json["dependencies"]:
                    print("*** Removing component:",entry)
                    del idf_component_json["dependencies"][entry]
                    # Track removed component for include cleanup (convert to filesystem format)
                    filesystem_name = convert_component_name_to_filesystem(entry)
                    removed_components.add(filesystem_name)

        if idf_custom_component_add != "":
            for entry in idf_custom_component_add:
                if len(str(entry)) > 4: # too short or empty entry
                    # add new entrys to json
                    if "@" in entry:
                        idf_comp_entry = str(entry.split("@")[0]).replace(" ", "")
                        idf_comp_vers = str(entry.split("@")[1]).replace(" ", "")
                    else:
                        idf_comp_entry = str(entry).replace(" ", "")
                        idf_comp_vers = "*"
                    if idf_comp_entry not in idf_component_json["dependencies"]:
                        print("*** Adding component:", idf_comp_entry, idf_comp_vers)
                        new_entry = {idf_comp_entry: {"version": idf_comp_vers}}
                        idf_component_json["dependencies"].update(new_entry)

        idf_component_yml_file = open(yml_file_dir,"w")
        yaml.dump(idf_component_json, idf_component_yml_file)
        idf_component_yml_file.close()
        
        # Clean up removed components if any were removed
        if removed_components:
            cleanup_removed_components()
        
        # print("JSON from modified idf_component.yml:")
        # print(json.dumps(idf_component_json))
        return
    return

def convert_component_name_to_filesystem(component_name):
    """Convert component name from registry format to filesystem format"""
    # Convert "espressif/esp32-camera" to "espressif__esp32-camera"
    # Replace "/" with "__"
    filesystem_name = component_name.replace("/", "__")
    return filesystem_name

def backup_pioarduino_build_py():
    """Create backup of the original pioarduino-build.py"""
    if not "arduino" in env.subst("$PIOFRAMEWORK"):
        return
    import shutil
    
    build_py_path = os.path.join(arduino_libs_mcu, "pioarduino-build.py")
    backup_path = os.path.join(arduino_libs_mcu, "pioarduino-build.py."+mcu)
    
    if os.path.exists(build_py_path):
        shutil.copy2(build_py_path, backup_path)
        print(f"*** Created backup of pioarduino-build.py for: {mcu}")

def cleanup_removed_components():
    """Clean up removed components and restore original build file"""
    
    for component in removed_components:
        # Remove include directories only
        include_path = os.path.join(arduino_libs_mcu, "include", component)
        if os.path.exists(include_path):
            shutil.rmtree(include_path)
            print(f"*** Removed include directory: {component}")
    
    # Remove CPPPATH entries from pioarduino-build.py
    remove_cpppath_entries()

def remove_cpppath_entries():
    """Remove CPPPATH entries for removed components from pioarduino-build.py"""
    import re
    
    build_py_path = os.path.join(arduino_libs_mcu, "pioarduino-build.py")
    
    if not os.path.exists(build_py_path):
        return
    
    with open(build_py_path, 'r') as f:
        content = f.read()
    
    # Remove CPPPATH entries for each removed component
    for component in removed_components:
        # Pattern to match lines like: join(PIO_SDK, "include", "espressif__esp32-camera"),
        pattern = rf'.*join\([^,]*,\s*"include",\s*"{re.escape(component)}"[^)]*\),?\n'
        content = re.sub(pattern, '', content)
        print(f"*** Removed CPPPATH entry for: {component}")
    
    with open(build_py_path, 'w') as f:
        f.write(content)

def restore_pioarduino_build_py(source, target, env):
    """Restore the original pioarduino-build.py from backup"""
    if not "arduino" in env.subst("$PIOFRAMEWORK"):
        return
    import shutil
    
    build_py_path = os.path.join(arduino_libs_mcu, "pioarduino-build.py")
    backup_path = os.path.join(arduino_libs_mcu, "pioarduino-build.py."+mcu)
    
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, build_py_path)
        os.remove(backup_path)  # Clean up backup file
        print(f"*** Restored original pioarduino-build.py for: {mcu}")
