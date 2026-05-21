from pathlib import Path
import yaml

# merges multiple yaml files
def merge_dicts(base, new):
    for key, value in new.items():
        if(
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            merge_dicts(base[key], value)
        else:
            base[key] = value
    return base  


# load all yaml files containing "config" in their name 
def load_configs(config_folder="config"):
    config = {}

    for file in Path(config_folder).glob("*config*.yaml"):
        with open(file, "r") as yaml_file:
            data = yaml.safe_load(yaml_file)
            if data:
                merge_dicts(config, data)
    return config         