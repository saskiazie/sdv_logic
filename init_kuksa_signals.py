import time 
from config_loader import load_configs # config files 
from kuksa_connection import KuksaConnection 

def reset_vehicle_signals(kuksa, verbose=True):
    if verbose:
        print("\n==== KuksaInit Info: Initialization of Vehicle Baseline State ====")

    def log(message):
        if verbose:
            print(message)

    # 1. close all relevant doors (set to false)
    log("--- Closing passenger door...")
    kuksa.publish("Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen", False)

    log("--- Closing driver door...")
    kuksa.publish("Vehicle.Cabin.Door.Row1.DriverSide.IsOpen", False)

    # 3. shut down engine (set to false)
    log("--- Ensuring engine is stopped...")
    kuksa.publish("Vehicle.Powertrain.CombustionEngine.IsRunning", False)           

    # Clear any active actuators/lights
    log("--- Resetting hazard lights ...")
    kuksa.publish("Vehicle.Body.Lights.Hazard.IsSignaling", False)        

    log("--- Turning off interior ambient light...")
    kuksa.publish("Vehicle.Cabin.Light.AmbientLight.IsLightOn", False)  

    # Basic vehicle motion state
    log("--- Resetting vehicle speed...")
    kuksa.publish("Vehicle.Speed", 0.0) 

    log("--- Resetting gear to park...")
    kuksa.publish("Vehicle.Powertrain.Transmission.CurrentGear", 126)     

    log("--- Resetting PDC rear active...")
    kuksa.publish("Vehicle.ADAS.PDC.Rear.IsActive", False)   

    log("--- Resetting PDC distance...")
    kuksa.publish("Vehicle.ADAS.PDC.Rear.Distance", 999.0)           

    log("--- Resetting backup light...")
    kuksa.publish("Vehicle.Body.Lights.Backup.IsOn", False)           

    log("--- Resetting low voltage system state...") # platzhalter für eigentliches signal 
    kuksa.publish("Vehicle.LowVoltageSystemState", "LOCK")   

# sobald signale im mapping existieren 
   # log("---Resetting ignition state...")
   # kuksa.publish("Vehicle.Body.IgnitionState", 0)        

    if verbose:
        print("\n[SUCCESS] Baseline state deployed via kuksa_connection wrapper")
        print("Your databroker is cleared\n\n")

def main():
    try: 
        config = load_configs()
        kuksa = KuksaConnection(host=config["kuksa"]["host"], 
                                port=config["kuksa"]["port"]) 
        print("---- Connecting to KUKSA ----")

        if not kuksa.connect():
            print("[ERROR] Could not connect to KUKSA")
            return 
        
        reset_vehicle_signals(kuksa, verbose=True)

    except Exception as e:
        print(f"\n[ERROR] Automation setup failed: {e}")

if __name__ == "__main__":
    main()    



'''

def reset_vehicle_signals():
    print ("\n\n==== KuksaInit Info: Initialization of Vehicle Baseline State ====")

    try:
        config = load_configs() # load all available config files *yaml
        kuksa = KuksaConnection(host=config["kuksa"]["host"], 
                                port=config["kuksa"]["port"]) 
        print("---- Connecting to KUKSA ----")
        kuksa.connect()

# Setting signal states for StartSequence
        # 1. close all relevant doors (set to false)
        print("--- Closing passenger door...")
        kuksa.publish("Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen", False)

        print("--- Closing driver door...")
        kuksa.publish("Vehicle.Cabin.Door.Row1.DriverSide.IsOpen", False)

        # 3. shut down engine (set to false)
        print("--- Ensuring engine is stopped...")
        kuksa.publish("Vehicle.Powertrain.CombustionEngine.IsRunning", False)           

        # Clear any active actuators/lights
        print("--- Resetting hazard lights ...")
        kuksa.publish("Vehicle.Body.Lights.Hazard.IsSignaling", False)        

        print("--- Turning off interior ambient light...")
        kuksa.publish("Vehicle.Cabin.Light.AmbientLight.IsLightOn", False)  

        # Basic vehicle motion state
        print("--- Resetting vehicle speed...")
        kuksa.publish("Vehicle.Speed", 0.0) 

        print("--- Resetting gear to park...")
        kuksa.publish("Vehicle.Powertrain.Transmission.CurrentGear", 126)     

        print("--- Resetting PDC rear active...")
        kuksa.publish("Vehicle.ADAS.PDC.Rear.IsActive", False)   

        print("--- Resetting PDC distance...")
        kuksa.publish("Vehicle.ADAS.PDC.Rear.Distance", 999.0)           

        print("--- Resetting backup light...")
        kuksa.publish("Vehicle.Body.Lights.Backup.IsOn", False)           

        print("--- Resetting low voltage system state...") # platzhalter für eigentliches signal 
        kuksa.publish("Vehicle.LowVoltageSystemState", "LOCK")           




        print("\n[SUCCESS] Baseline state deployed via kuksa_connection wrapper")
        print("Your databroker is cleared\n\n\n")


    except Exception as e:
        print(f"\n[ERROR] Automation setup failed: {e}")
        print("Please verify that KUKSA Databroker is actively running")

if __name__ == "__main__":
    reset_vehicle_signals()        
'''