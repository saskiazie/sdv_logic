from pathlib import Path

import yaml

def merge_dicts(base, new):
    '''Recursively merge dict "new" into dict "base" (in place).

    Nested dicts are merged key by key; all other values in "new"
    overwrite the ones in "base".
    '''
    for key, value in new.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            merge_dicts(base[key], value)
        else:
            base[key] = value
    return base


def load_configs(config_folder="config"):
    '''Load and merge all *config*.yaml files from the config folder.

    Purpose:
        Allows the configuration to be split over several YAML files
        (e.g. one per domain). All files matching *config*.yaml are
        merged into one dict; later files can override earlier keys.

    Returns:
        dict with the merged configuration
    '''
    config = {}
    for file in Path(config_folder).glob("*config*.yaml"):
        with open(file, "r") as yaml_file:
            data = yaml.safe_load(yaml_file)
            if data:
                merge_dicts(config, data)
    return config