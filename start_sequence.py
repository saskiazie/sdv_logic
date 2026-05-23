import time # for waiting time

class StartSequence:
    '''
    Logic for vehicle unlocking and startup sequence
    - Passenger door open acts as a temporary unlock request trigger
    - hazard lights blink twice asynchronously upon lock
    - interior light turns on upon unlock 
    - Opening the drivers door grants access 
    '''

# PassengerSide = Unlock Request -> Unlock detected + Hazard Lights twice + Interior Light # temporary access signal
# DriverSide = Door open -> Access granted 

    # Input signals
    # Trigger Unlock SDV with opening PassengerSide Row1
    UNLOCK_REQUEST_SIGNAL = "Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen" # temporary # Vehicle.Body.Locks.IsLocked ??? existiert das 
    DOOR_OPEN_SIGNAL = "Vehicle.Cabin.Door.Row1.DriverSide.IsOpen"

# Added Signal (?) VSS Actuator ignition switch state (uint8 Enum) - NEW!!
    # Mapping: 0 = LOCK, 1 = OFF, 2 = ACC, 3 = ON (für Vehicle.LowVoltageSystemState braucht man aber Strings (nur zu Testzwecken) )
    IGNITION_STATE_SIGNAL =  "Vehicle.LowVoltageSystemState" #"Vehicle.Body.IgnitionState" ignition state ist int - voltagesystemstate arbeitet mit string

    # Output signals
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"
    INTERIOR_LIGHT_SIGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn" #"Vehicle.Cabin.Light.AmbientLight.Row2.DriverSide.IsLightOn" 
    ENGINE_RUNNING_SIGNAL = "Vehicle.Powertrain.CombustionEngine.IsRunning" # official VSS Signal: true if engine is active (rpm>0)

    # Initializes the start sequence module with KUKSA and internal states 
    def __init__(self, kuksa, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state # global variable
        self.unlock_done = False
        self.unlock_triggered = False # flag for unlock vehicle
        self.last_door_open = False
        self.ignition_on_triggered = False # Flag to ensure for jsut running once

        # Internal states for asynchronous hazard blinking withput blocking thread
        self.blink_active = False
        self.blink_start_time = 0.0
        self.blink_count = 0


    # Function Defintition for Blink hazard light twice
    def trigger_hazard_blink(self, current_time):
        if not self.blink_active:
            return

        elapsed = current_time - self.blink_start_time

        # first blink: turn on (0 to 0.4 sec)
        if elapsed < 0.4 and self.blink_count == 0:
            self.kuksa.set(self.HAZARD_SIGNAL, True)
            self.blink_count = 1
        # first blink: turn off (0.4 to 0.8 sec)    
        elif 0.4 <= elapsed < 0.8 and self.blink_count == 1:
            self.kuksa.set(self.HAZARD_SIGNAL, False)
            self.blink_count = 2
        
        # second blink: turn on (0.8 to 1.2 sec)
        if 0.8 <= elapsed < 1.2 and self.blink_count == 2:
            self.kuksa.set(self.HAZARD_SIGNAL, True)
            self.blink_count = 3
        # second blink: turn off (1.2 to 1.6 sec)    
        elif 1.2 <= elapsed < 1.6 and self.blink_count == 3:
            self.kuksa.set(self.HAZARD_SIGNAL, False)
            self.blink_count = 4
        # End condition
        elif elapsed >= 1.6:
            self.kuksa.set(self.HAZARD_SIGNAL, False)
            self.blink_active = False # Deactivate blink state machine 



    # Executes the cyclic start of sequence logic 
    def run(self):
        current_time = time.time()

        # Read current sensor values from KUKSA
        unlock_request = bool(self.kuksa.get(self.UNLOCK_REQUEST_SIGNAL, False))
        door_open = bool(self.kuksa.get(self.DOOR_OPEN_SIGNAL, False))

        # Read current ignition state as an integer (uint8), default 0 (LOCK)
        ignition_state = str(self.kuksa.get(self.IGNITION_STATE_SIGNAL, "LOCK")) # int hat Ignition state (für später) int(self.kuksa.get(self.IGNITION_STATE_SIGNAL, 0))

        # Step 1: Unlock detection
        if unlock_request is True and not self.unlock_done and not self.unlock_triggered:
            print("StartSequence Info: Unlock detected")
            self.unlock_triggered = True

            # Turn on interior light (ambient light)
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, True)
            self.unlock_done = True

            # schaltet dann frei für aklle
            self.vehicle_state["is_ready"] = True
            print("StartSequence Info: Vehicle state set to READY")

            # Arm the blinking function by setting start time and active flag
            self.blink_active = True
            self.blink_start_time = current_time
            self.blink_count = 0

        # Call blink funtion every cycle to process light state 
        self.trigger_hazard_blink(current_time)

        # Step 2: Driver Entry and Engine startup
        # Driver door opened 
        if door_open is True and not self.last_door_open and self.unlock_done:
            print("StartSequence Info: Driver door opened --> Access granted + waiting for ignition") 

        # Step 3: Ignition and Engine startup  
        if self.unlock_done:
            # Key Position 1 (0) LOCK
            # Key Position 2 (1) OFF
            # Key Position 3 (2) ACC 
            # Key Position 4 (3) ON

            if ignition_state == "ACC": #== 2: (für ignition state)  # Infotainemnt/ Radio activated 
                pass

            # 3 == ON in string
            elif ignition_state == "ON" and not self.ignition_on_triggered:   #== 3 and not self.ignition_on_triggered:
                print("StartSequence Info: Ignition State is ON (3) -> Triggered Check control simulation") 
                self.ignition_on_triggered = True

            # as long as ignition is on - controls engine 
            if ignition_state == "ON": #== 3:    
                is_engine_running = bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False))
                if not is_engine_running:
                    print("StartSequence Info: Activating Powertrain -> Engine IsRunning")
                    self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, True)

            # safety fallback: reset if user turns key back to LOCK 0 or OFF 1
        if ignition_state in ["LOCK", "OFF"]: #[0,1]:
            self.ignition_on_triggered = False
            #If ignition is cut off, immediately kill engine 
            if bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False)):
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, False)
                print("StartSequence Info: Ignition OFF/LOCK - Engine stopped ")

        # Save current door state for edge detection in next loop
        self.last_door_open = door_open    