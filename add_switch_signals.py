import json

VSS_FILE = "Own_GUI_vss.json"

# Die drei neuen Schalter-Signale (Absicht des Fahrers, bleibt konstant true/false)
NEW_SIGNALS = {
    "Vehicle.Body.Lights.Hazard.IsEnabled":
        "Hazard warning switch state (driver intent)",
    "Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled":
        "Left turn indicator switch state (driver intent)",
    "Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled":
        "Right turn indicator switch state (driver intent)",
}

def insert_signal(tree, path, description):
    """Laeuft den VSS-Baum entlang des Pfads und haengt das Signal als Leaf an."""
    parts = path.split(".")
    node = tree
    # bis zum Eltern-Knoten durchhangeln (alle Teile ausser dem letzten)
    for part in parts[:-1]:
        if part in node:
            node = node[part]
        elif "children" in node and part in node["children"]:
            node = node["children"][part]
        else:
            print(f"[FEHLER] Pfad-Teil '{part}' nicht gefunden fuer {path}")
            print("         -> Existiert der Elternpfad in deiner JSON? (CLI/TAB pruefen)")
            return False
        # in die children-Ebene absteigen, falls vorhanden
    # Eltern-Knoten braucht ein children-Dict
    if "children" not in node:
        node["children"] = {}
    leaf_name = parts[-1]
    if leaf_name in node["children"]:
        print(f"[SKIP] {path} existiert schon")
        return True
    node["children"][leaf_name] = {
        "datatype": "boolean",
        "type": "actuator",
        "description": description,
    }
    print(f"[OK] {path} hinzugefuegt")
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
        print("\n[FERTIG] Own_GUI_vss.json aktualisiert. Broker neu starten!")
    else:
        print("\n[ABBRUCH] Nichts gespeichert - Pfadproblem oben pruefen.")

if __name__ == "__main__":
    main()