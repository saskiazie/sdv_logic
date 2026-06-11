import time 
import threading
import traceback

# Custom utility odules for externalized architecture 
from config_loader import load_configs # config files 
from kuksa_connection import KuksaConnection

# SDV decentralized logic modules 
from start_sequence import StartSequence 
from auto_lock import AutoLock
from powertrain_safety_logic import PowertrainSafetyLogic
from pdc_logic import PDCLogic
from lights_logic import LightsLogic

# Runs one logic module per cycle in its own thread
def run_logic(logic_module, cycle_time=0.1):
    while True:
        try:
            logic_module.run()
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)[-1]
            filename = tb.filename.split("/")[-1]
            line_number = tb.lineno

            print(f"Execution Error in [{logic_module.__class__.__name__}] ({filename} -> Line {line_number}): {e}")
        time.sleep(cycle_time)

# main loop
def main():
    # 1. Initialization Phase: Load all external configurations from YAML files
    config = load_configs() # load all available config files *yaml

    # 2. Connection: Initialization of KUKSA Databroker interface
    kuksa = KuksaConnection(host=config["kuksa"]["host"], 
                            port=config["kuksa"]["port"]) 
    
    # Establish connection to KUKSA Databroker
    # "Safety gate": If the connection fails, stop execution immediatly
    if not kuksa.connect():
        print("Program stopped because KUKSA is not available!")
        return
    
    # Central vehicle state management 
    # this shared dictionary acts as a decentralized state crdinator between threads
    # StartSequence will unlock the vehicle system, making it available for other functions
    vehicle_state = {
        "is_locked": True, # System flag (False = Vehicle locked)
        "is_unlocked": False,
        "driver_access": False,
        "is_ready": False,
    }

    # 3. Initialize logic classes (all of them)
    start_sequence = StartSequence(kuksa, vehicle_state)
    auto_lock = AutoLock(kuksa, config["autolock"], vehicle_state) 
    powertrain_safety_logic = PowertrainSafetyLogic(kuksa, config["powertrain"], vehicle_state)
    pdc_logic = PDCLogic(kuksa, config["pdc"], vehicle_state)
    lights_logic = LightsLogic(kuksa, vehicle_state)

        
    # 4. Grouping modules for automated threading     
    logic_modules = [
        start_sequence,
        auto_lock,
        powertrain_safety_logic,
        pdc_logic,
        lights_logic,
    ]   

    print ("SDV Logic Code started") # Control message

    # 5. Multi threading Execution
    for logic_module in logic_modules:
        # determine base system cycle time from YAML configs (fallback 0.1s)
        chosen_cycle_time = config.get("system", {}).get("cycle_time", 0.1)

        # check if the module has an individual cycle time parameter 
        # allows individual control (some modules can run faster than others if necessary)
        if hasattr(logic_module, 'config') and isinstance (logic_module.config, dict):
            chosen_cycle_time = logic_module.config.get("cycle_time", chosen_cycle_time)

        # Spawn the thread with the final evaluated timing parameter 
        threading.Thread(
            target=run_logic,
            args=(logic_module,chosen_cycle_time),
            daemon=True # threads will automatically terminate when the main loop process exits
        ).start()
    
    # "Keep Alive Loop" keeps the main thread running 
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("SDV Logic main loop interrupted by user")

if __name__ == "__main__":
    main()    






