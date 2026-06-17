import time 
from config_loader import load_configs # config files 
from kuksa_connection import KuksaConnection 

def reset_vehicle_signals(kuksa, verbose=True):
    '''
    sets all relevant vehicle signals to a defined baseline state.
    - each publish() call is individually secured
    - is a signal (not yet) present in the KUKSA mapping, the error is caught and logged
    - return: list of failed (unmapped) signals
    '''

    if verbose:
        print("\n==== KuksaInit Info: Initialization of Vehicle Baseline State ====")

    failed = []

    def log(message):
        if verbose:
            print(message)

    def safe_publish(signal, value):
        try:
            kuksa.publish(signal, value)
        except Exception as e:
            failed.append(signal)
            log(f"  [WARN] Signal not set (possibly not mapped): {signal} -> {e}")



    # 1. close all relevant doors (set to false)
    log("--- Closing passenger door...")
    safe_publish("Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen", False)

    log("--- Closing driver door...")
    safe_publish("Vehicle.Cabin.Door.Row1.DriverSide.IsOpen", False)

    # 3. shut down engine (set to false)
    log("--- Ensuring engine is stopped...")
    safe_publish("Vehicle.Powertrain.CombustionEngine.IsRunning", False)           

    # Clear any active actuators/lights
    log("--- Resetting hazard lights ...")
    safe_publish("Vehicle.Body.Lights.Hazard.IsSignaling", False)        

    log("--- Turning off interior ambient light...")
    safe_publish("Vehicle.Cabin.Light.AmbientLight.IsLightOn", False)  

    # Basic vehicle motion state
    log("--- Resetting vehicle speed...")
    safe_publish("Vehicle.Speed", 0.0) 

    log("--- Resetting gear to park...")
    safe_publish("Vehicle.Powertrain.Transmission.CurrentGear", 126)     

    log("--- Resetting PDC rear active...")
    safe_publish("Vehicle.ADAS.PDC.Rear.IsActive", False)   

    log("--- Resetting PDC distance...")
    safe_publish("Vehicle.ADAS.PDC.Rear.Distance", 999.0)           

    log("--- Resetting backup light...")
    safe_publish("Vehicle.Body.Lights.Backup.IsOn", False)           

    log("--- Resetting low voltage system state...") # platzhalter für eigentliches signal 
    safe_publish("Vehicle.LowVoltageSystemState", "LOCK")   

# sobald signale im mapping existieren 
    #log("--- Resetting ignition state...")
    #safe_publish("Vehicle.Body.IgnitionState", 0)        

    #log("--- Resetting access keyfob state...")
    #safe_publish("Vehicle.Body.Access.KeyFob.IsUnlocked", False)        

    if verbose:
        if failed:
            print("\n[InitKuksaSignals WARN] Baseline set, but the following signals are not mapped:")
            for sig in failed:
                print(f"        - {sig}")
            print("     -> Include these paths in the VSS mapping, then check again")    
        else:
            print("\n[SUCCESS] Baseline state deployed via kuksa_connection wrapper")
            print("Your databroker is cleared\n")

    return failed        

def main():
    try: 
        config = load_configs()
        kuksa = KuksaConnection(host=config["kuksa"]["host"], 
                                port=config["kuksa"]["port"]) 
        print("---- Connecting to KUKSA ----")

        if not kuksa.connect():
            print("[ERROR] Could not connect to KUKSA")
            return 
        
        failed = reset_vehicle_signals(kuksa, verbose=True)

        if failed:
            print(f"[CHECK] {len(failed)} Signals not mapped\n\n")
        else:
            print("[CHECK] All Baseline states mapped\n\n")

    except Exception as e:
        print(f"\n[ERROR] Automation setup failed: {e}")

if __name__ == "__main__":
    main()    



