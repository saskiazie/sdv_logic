import json

# as an example how to add signals 
'''
One-time utility: adds the three indicator SWITCH signals to the VSS
mapping (Own_GUI_vss.json).

Purpose:
    The switch signals represent driver intent (constant true/false)
    and are deliberately separated from the IsSignaling light states,
    which are toggled by IndicatorLogic. Run once, then restart the
    databroker.

Notes:
    - Safe to re-run: existing signals are skipped.
    - Nothing is written if any parent path is missing.
'''

VSS_FILE = "Own_GUI_vss.json"

# The three switch signals (driver intent, constant true/false)
NEW_SIGNALS = {
    "Vehicle.Body.Lights.Hazard.IsEnabled":
        "Hazard warning switch state (driver intent)",
    "Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled":
        "Left turn indicator switch state (driver intent)",
    "Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled":
        "Right turn indicator switch state (driver intent)",
}


def insert_signal(tree, path, description):
    '''Walk the VSS tree along the path and attach the signal as a leaf.'''
    parts = path.split(".")
    node = tree

    # walk down to the parent node (all parts except the last)
    for part in parts[:-1]:
        if part in node:
            node = node[part]
        elif "children" in node and part in node["children"]:
            node = node["children"][part]
        else:
            print(f"[AddSwitchSignals] Error: path part '{part}' "
                  f"not found for {path}")
            print("    -> Does the parent path exist in your JSON? "
                  "(check via CLI/TAB)")
            return False

    # the parent node needs a children dict
    if "children" not in node:
        node["children"] = {}

    leaf_name = parts[-1]
    if leaf_name in node["children"]:
        print(f"[AddSwitchSignals] Skip: {path} already exists")
        return True

    node["children"][leaf_name] = {
        "datatype": "boolean",
        "type": "actuator",
        "description": description,
    }
    print(f"[AddSwitchSignals] Info: {path} added")
    return True


def main():
    with open(VSS_FILE, "r", encoding="utf-8") as f:
        tree = json.load(f)

    ok = True
    for path, desc in NEW_SIGNALS.items():
        ok = insert_signal(tree, path, desc) and ok

    if ok:
        with open(VSS_FILE, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=2)
        print("\n[AddSwitchSignals] Done: Own_GUI_vss.json updated. "
              "Restart the databroker!")
    else:
        print("\n[AddSwitchSignals] Aborted: nothing saved - "
              "check the path problem above.")


if __name__ == "__main__":
    main()