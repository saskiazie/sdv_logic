import time
import threading
import traceback

# Custom utility modules for the externalized architecture
from config_loader import load_configs
from kuksa_connection import KuksaConnection

# SDV decentralized logic modules
from start_sequence import StartSequence
from auto_lock import AutoLock
from powertrain_safety_logic import PowertrainSafetyLogic
from pdc_logic import PDCLogic
from lights_logic import LightsLogic
from indicator_logic import IndicatorLogic
from unreal_sender import UnrealSender

from init_kuksa_signals import reset_vehicle_signals

# Fast lane cycle time for modules that need smooth visual output
# (blinking lights and the TCP stream to Unreal)
FAST_LANE_CYCLE_S = 0.02


def run_logic(logic_module, cycle_time=0.1):
    '''Runs one logic module cyclically in its own thread.

    Exceptions are caught and logged with file and line number so a
    single faulty module can never take down the whole system.
    '''
    while True:
        try:
            logic_module.run()
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)[-1]
            filename = tb.filename.split("/")[-1]
            line_number = tb.lineno
            print(f"[Main] Error: execution error in "
                  f"[{logic_module.__class__.__name__}] "
                  f"({filename} -> line {line_number}): {e}")
        time.sleep(cycle_time)


def main():
    # 1. Initialization: load all external configurations (YAML)
    config = load_configs()

    # 2. Connection: initialize the KUKSA databroker interface.
    # Safety gate: if the connection fails, stop execution immediately.
    kuksa = KuksaConnection(host=config["kuksa"]["host"],
                            port=config["kuksa"]["port"])
    if not kuksa.connect():
        print("[Main] Error: program stopped because KUKSA is not available")
        return

    # 3. Reset all relevant vehicle signals to a defined baseline state
    reset_vehicle_signals(kuksa, verbose=False)
    #kuksa.publish("Vehicle.Body.Access.KeyFob.IsUnlocked", False)
    #kuksa.publish("Vehicle.Body.IgnitionState", 0)

    # 4. Central vehicle state management.
    # This shared dictionary acts as the state coordinator between the
    # module threads. StartSequence unlocks the vehicle system, making
    # it available for the other functions.
    # Note: plain dict without a lock - all writers set simple boolean
    # flags, which is atomic enough under the CPython GIL (documented
    # design decision).
    vehicle_state = {
        "is_locked": True,       # True = vehicle is locked
        "is_unlocked": False,    # True = unlocked (access phase)
        "driver_access": False,  # True = driver door was opened
        "is_ready": False,       # True = ignition ON accepted
    }

    # 5. Initialize all logic modules
    start_sequence = StartSequence(kuksa, vehicle_state)
    auto_lock = AutoLock(kuksa, config["autolock"], vehicle_state)
    powertrain_safety_logic = PowertrainSafetyLogic(kuksa, config["powertrain"], vehicle_state)
    pdc_logic = PDCLogic(kuksa, config["pdc"], vehicle_state)
    lights_logic = LightsLogic(kuksa, vehicle_state)
    indicator_logic = IndicatorLogic(kuksa, vehicle_state)
    unreal_sender = UnrealSender(kuksa, vehicle_state, port=7010)

    # 6. Group modules for automated threading
    logic_modules = [
        start_sequence,
        auto_lock,
        powertrain_safety_logic,
        pdc_logic,
        lights_logic,
        indicator_logic,
        unreal_sender,
    ]

    print("[Main] Info: SDV logic started")

    # 7. Multi-threaded execution: one thread per module
    base_cycle_time = config.get("system", {}).get("cycle_time_s", 0.1)

    for logic_module in logic_modules:
        chosen_cycle_time = base_cycle_time

        # Fast lane: blinking lights and the Unreal stream need a
        # faster cycle for smooth operation
        if isinstance(logic_module, (LightsLogic, IndicatorLogic, UnrealSender)):
            chosen_cycle_time = FAST_LANE_CYCLE_S

        threading.Thread(
            target=run_logic,
            args=(logic_module, chosen_cycle_time),
            daemon=True,  # threads terminate when the main process exits
        ).start()

    # Keep-alive loop: keeps the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Main] Info: SDV logic stopped by user")


if __name__ == "__main__":
    main()