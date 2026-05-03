import time 
import threading

from kuksa_connection import KuksaConnection
from start_sequence import StartSequence 
from auto_lock import AutoLock
from powertrain_safety_logic import PowertrainSafetyLogic
from pdc_logic import PDCLogic

# Runs one logic module per cycle in its own thread
def run_logic(logic_module, cycle_time=0.1):
    while True:
        logic_module.run()
        time.sleep(cycle_time)

# main loop
def main():
    # Definition of KUKSA Databroker with IP-Adress
    kuksa = KuksaConnection(host="127.0.0.1", port=55555)
    
    # Establish connection to KUKSA Databroker
    # If the connection fails, the program is stopped
    if not kuksa.connect():
        print("Program stopped because KUKSA is not available!")
        return

    # ------- Initialize logic classes (all of them) --------
    start_sequence = StartSequence(kuksa)
    auto_lock = AutoLock(kuksa) 
    powertrain_safety_logic = PowertrainSafetyLogic(kuksa)
    pdc_logic = PDCLogic(kuksa)
        
    # needed for thread
    logic_modules = [
        start_sequence,
        auto_lock,
        powertrain_safety_logic,
        pdc_logic,
    ]   

    print ("SDV Logic Code started") # Kontrolle

    for logic_module in logic_modules:
        threading.Thread(
            target=run_logic,
            args=(logic_module,),
            daemon=True 
        ).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()    






