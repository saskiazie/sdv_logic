from config_loader import load_configs
from kuksa_connection import KuksaConnection


def reset_vehicle_signals(kuksa, verbose=True):
    '''
    Sets all relevant vehicle signals to a defined baseline state.

    Purpose:
        Brings the databroker into a known, clean state before the
        logic modules start (all doors closed, engine off, lights off,
        vehicle stationary in park).

    Input signals:
        none (write-only initialization)

    Output signals:
        see the safe_publish() calls below - one per baseline value

    Special notes:
        - Every publish is individually secured: if a signal is not
          (yet) present in the KUKSA mapping, the error is caught,
          logged and collected.
        - Returns the list of failed (unmapped) signals so callers can
          react (e.g. abort or warn).
    '''
    if verbose:
        print("\n==== [KuksaInit] Info: initializing vehicle baseline state ====")

    failed = []

    def log(message):
        if verbose:
            print(message)

    def safe_publish(signal, value):
        try:
            kuksa.publish(signal, value)
        except Exception as e:
            failed.append(signal)
            log(f"[KuksaInit] Warning: signal not set "
                f"(possibly not mapped): {signal} -> {e}")

    # 1. Close all relevant doors
    log("--- Closing passenger door...")
    safe_publish("Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen", False)
    log("--- Closing driver door...")
    safe_publish("Vehicle.Cabin.Door.Row1.DriverSide.IsOpen", False)

    # 2. Shut down the engine
    log("--- Ensuring engine is stopped...")
    safe_publish("Vehicle.Powertrain.CombustionEngine.IsRunning", False)

    # 3. Clear any active actuators / lights
    log("--- Resetting hazard lights...")
    safe_publish("Vehicle.Body.Lights.Hazard.IsSignaling", False)
    log("--- Turning off interior ambient light...")
    safe_publish("Vehicle.Cabin.Light.AmbientLight.IsLightOn", False)
 #   log("--- Resetting brake light...")
 #   safe_publish("Vehicle.Body.Lights.Brake.IsActive", "INACTIVE")

    # 4. Basic vehicle motion state
    log("--- Resetting vehicle speed...")
    safe_publish("Vehicle.Speed", 0.0)
    log("--- Resetting gear to park...")
    safe_publish("Vehicle.Powertrain.Transmission.CurrentGear", 126)

    # 5. Driver assistance baseline
    log("--- Resetting PDC rear active...")
    safe_publish("Vehicle.ADAS.PDC.Rear.IsActive", False)
    log("--- Resetting PDC distance...")
    safe_publish("Vehicle.ADAS.PDC.Rear.Distance", 999.0)
    log("--- Resetting backup light...")
    safe_publish("Vehicle.Body.Lights.Backup.IsOn", False)

    # 6. Power state (placeholder path until the real signal is mapped)
    log("--- Resetting low voltage system state...")
    safe_publish("Vehicle.LowVoltageSystemState", "LOCK")

    # 7. Ignition and key fob reset (to ensure the start sequence can run)
    log("--- Resetting ignition state...")
    safe_publish("Vehicle.Body.IgnitionState", 0)
    log("--- Resetting KeyFob state...")
    safe_publish("Vehicle.Body.Access.KeyFob.IsUnlocked", False)

    if verbose:
        if failed:
            print("\n[KuksaInit] Warning: baseline set, but the following "
                  "signals are not mapped:")
            for sig in failed:
                print(f"    - {sig}")
            print("    -> Include these paths in the VSS mapping, "
                  "then check again")
        else:
            print("\n[KuksaInit] Info: baseline state deployed successfully")
            print("[KuksaInit] Info: databroker is cleared\n")

    return failed


def main():
    try:
        config = load_configs()
        kuksa = KuksaConnection(host=config["kuksa"]["host"],
                                port=config["kuksa"]["port"])
        print("---- Connecting to KUKSA ----")
        if not kuksa.connect():
            print("[KuksaInit] Error: could not connect to KUKSA")
            return

        failed = reset_vehicle_signals(kuksa, verbose=True)
        if failed:
            print(f"[KuksaInit] Check: {len(failed)} signals not mapped\n")
        else:
            print("[KuksaInit] Check: all baseline states mapped\n")
    except Exception as e:
        print(f"\n[KuksaInit] Error: automation setup failed: {e}")


if __name__ == "__main__":
    main()