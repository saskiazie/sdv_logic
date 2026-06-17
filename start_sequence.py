import time # for waiting time
from init_kuksa_signals import reset_vehicle_signals

class StartSequence:
    '''
    Logic for vehicle access and startup sequence
    - Detect key fob unlock request
    - detect key fob lock request
    - validate driver access
    - validate ignition state 
    - set central vehicle states for other modules 
    - start and stop the engine 

    Lightning feedback is handled separately by LightsLogic.
    StartSequence only updates vehicle_state
    '''

    # Input signals
    # Key Fob unlock request
    KEYFOB_SIGNAL = "Vehicle.Body.Access.KeyFob.IsUnlocked" # NEW SIGNAL
    
    # True = Locked, False = Unlocked
    DRIVER_LOCK_SIGNAL = "Vehicle.Cabin.Door.Row1.DriverSide.IsLocked"

    # uint8 actuator
    IGNITION_STATE_SIGNAL = "Vehicle.Body.IgnitionState"

    ## Ignition state values 
    IGNITION_LOCK = 0
    IGNITION_OFF = 1
    IGNITION_ACC = 2
    IGNITION_ON = 3

    # Output signals
    ENGINE_RUNNING_SIGNAL = "Vehicle.Powertrain.CombustionEngine.IsRunning"

    def __init__(self, kuksa, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state # global variable

        self.unlock_done = False
        self.lock_done = True # flag for unlock vehicle
        self.ignition_on_triggered = False # Flag to ensure for jsut running once
        self.driver_entry_done = False
        self.ignition_missing_entry_warning_printed = False
        self.ignition_acc_triggered = False 

    def run(self):
        keyfob_unlocked = bool(self.kuksa.get(self.KEYFOB_SIGNAL, False))
        driver_door_locked = bool(self.kuksa.get(self.DRIVER_LOCK_SIGNAL, True))
        ignition_state = int(self.kuksa.get(self.IGNITION_STATE_SIGNAL, self.IGNITION_LOCK))


        # ----------------
        # 1. Unlock Request
        if keyfob_unlocked and not self.unlock_done:
            print("StartSequence Info: Key fob unlock request detected")

            #clear old runtime values from previous simulation cycles 
            #reset_vehicle_signals(self.kuksa, verbose=False)

            self.vehicle_state["is_locked"] = False
            self.vehicle_state["is_unlocked"] = True
            self.vehicle_state["driver_access"] = False                      
            self.vehicle_state["is_ready"] = False

            self.unlock_done = True
            self.lock_done = False
            self.driver_entry_done = False
            self.ignition_on_triggered = False
            self.ignition_missing_entry_warning_printed = False

            print("StartSequence Info: Vehicle state set to UNLOCKED")

        # ----------------
        # 2. Lock Request
        if not keyfob_unlocked and not self.lock_done:
            print("StartSequence Info: Key fob lock request detected")

            self.vehicle_state["is_locked"] = True
            self.vehicle_state["is_unlocked"] = False
            self.vehicle_state["driver_access"] = False                      
            self.vehicle_state["is_ready"] = False

            self.unlock_done = False
            self.lock_done = True
            self.driver_entry_done = False
            self.ignition_on_triggered = False
            self.ignition_missing_entry_warning_printed = False

            if bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False)):
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, False)
                print("StartSequence Info: Engine stopped due to lock request")

            print("StartSequence Info: Vehicle state set to LOCKED")    


        # ----------------
        # 3. Driver access validation 
        if(self.unlock_done and not driver_door_locked and not self.driver_entry_done):
            self.vehicle_state["driver_access"] = True 
            self.driver_entry_done = True
            self.ignition_missing_entry_warning_printed= False

            print("StartSequence Info: Driver door unlocked --> Access granted + waiting for ignition")

        # ----------------
        # 4. Ignition validation
        if self.unlock_done and ignition_state == self.IGNITION_ACC:
                 
            if not self.ignition_acc_triggered:
                print("StartSequence Info: Ignition ACC detected")
                self.ignition_acc_triggered = True


        elif self.unlock_done and ignition_state == self.IGNITION_ON:
            if not self.driver_entry_done:
                if not self.ignition_missing_entry_warning_printed:
                    print("StartSequence Warning: Ignition ignored - driver access missing")
                    self.ignition_missing_entry_warning_printed = True
                return

            if not self.ignition_on_triggered:
                self.vehicle_state["is_ready"] = True
                self.ignition_on_triggered = True

                print("StartSequence Info: Ignition ON accepted")
                print("StartSequence Info: Vehicle state set to READY")


        # ----------------
        # 5. Engine startup
        if(self.vehicle_state.get("is_ready", False) and ignition_state == self.IGNITION_ON):
            is_engine_running = bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False))

            if not is_engine_running:
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, True)
                print("StartSequence Info: Engine started")


        # ----------------
        # 6. Ignition off / lock fallback
        if ignition_state in [self.IGNITION_LOCK, self.IGNITION_OFF]:
            self.ignition_on_triggered = False
            self.ignition_acc_triggered = False

            self.vehicle_state["is_ready"] = False

            if bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False)):
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, False)
                print("StartSequence Info: Ignition OFF/LOCK - Engine stopped")

   