import time 
from config_loader import load_configs # config files 
from kuksa_connection import KuksaConnection 

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
        kuksa.publish("Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen", "false")

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

        print("\n[SUCCESS] Baseline state deployed via kuksa_connection wrapper")
        print("Your databroker is cleared\n\n\n")


    except Exception as e:
        print(f"\n[ERROR] Automation setup failed: {e}")
        print("Please verify that KUKSA Databroker is actively running")

if __name__ == "__main__":
    reset_vehicle_signals()        
