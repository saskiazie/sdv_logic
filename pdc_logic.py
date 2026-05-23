import time 

class PDCLogic:
    '''
    Handles the Park Distance Control (PDC) safety  and reverse backup light logic
    - Activates automatically when the vehicle is in reverse and the engine is running 
    - Measures obstacle distance using non-blocking cyclic timing to calculate a dynamic warning beep with buzzer
    - Automatically activates vehicles backup light when reverse gear is engaged 
    - With non-blocking structure for threads
    '''

    # Input Signal
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"
    ENGINE_RUNNING_SIGNAL = "Vehicle.Powertrain.CombustionEngine.IsRunning"

    # Output Signal
    PDC_REAR_ACTIVE_SIGNAL = "Vehicle.ADAS.PDC.Rear.IsActive"
    DISTANCE_SENSOR_SIGNAL = "Vehicle.ADAS.PDC.Rear.Distance" # Value in cm
    BACKUP_LIGHT_SIGNAL = "Vehicle.Body.Lights.Backup.IsOn"

    # acoustic cabin warning
    # Sends frequency states: 0 = silent, 1 = slow beep, 2 = rapid beep, 3 = solid beep
    BUZZER_SIGNAL = "Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime" # TBD !!!
    
    def __init__(self, kuksa, config, vehicle_state):
        self.kuksa = kuksa
        self.reverse_gear_threshold = config["reverse_gear_threshold"]
        self.pdc_active = False
        self.vehicle_state = vehicle_state

        # Internal states 
        self.last_action_time = 0.0
        self.buzzer_toggle = False

    # Helper functions
    def is_reverse(self,gear):
        return gear < self.reverse_gear_threshold

    # helper function for KUKSA if signalnot available 
    def safe_kuksa_set(self, signal, value):
        try:
            self.kuksa.set(signal, value)
        except Exception:
            pass

    def trigger_intermittent_buzzer(self, current_time, interval, active_level):
        # asynchronous pulse generator to prevent blocking th ethread loop
        if current_time - self.last_action_time >= interval:
            self.last_action_time = current_time
            self.buzzer_toggle = not self.buzzer_toggle

            #Pulse the tone state based on toggle
            target_value = active_level if self.buzzer_toggle else 0
            self.safe_kuksa_set(self.BUZZER_SIGNAL, target_value)


    def run(self):
        current_time = time.time()

        # Read current values
        try:
            gear = int(self.kuksa.get(self.GEAR_SIGNAL, 0))
            is_engine_running = bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False))
            distance_cm = float(self.kuksa.get(self.DISTANCE_SENSOR_SIGNAL, 999.0))
        except Exception as e:
            print(f"PDC Error: Databroker connection dropped: {e}")
            return 
        
        # Step 1: System activation and backup light 
        if is_engine_running and self.is_reverse(gear):
            # Turn on reverse light 
            self.kuksa.set(self.BACKUP_LIGHT_SIGNAL, True)

            # activating rear parking sensor 
            if not self.pdc_active:
                self.kuksa.set(self.PDC_REAR_ACTIVE_SIGNAL, True)
                self.pdc_active = True
                print("PDC Info: Rear praking sensor activated")

        else:
            # clean off and forcing everything to turn off when leaving reverse gear
            if self.pdc_active or self.is_reverse(gear):
                self.kuksa.set(self.BACKUP_LIGHT_SIGNAL, False)
                self.kuksa.set(self.PDC_REAR_ACTIVE_SIGNAL, False)
                self.safe_kuksa_set(self.BUZZER_SIGNAL, 0) # Mute buzzer 
                self.pdc_active = False
                self.buzzer_toggle = False
                print("PDC Info: Rear Parking sensor and backup lights deactivated")
            return

        # Step 2
        # distance evaluation and mapping
        if distance_cm > 150.0:
            self.safe_kuksa_set(self.BUZZER_SIGNAL, 0)
            self.buzzer_toggle = False 
            return 
        
        elif distance_cm > 100.0:
            # slow beep 
            beep_interval = 0.8
            warning_level = 1
        
        
        elif distance_cm > 50.0:
            # rapid beep 
            beep_interval = 0.3
            warning_level = 2

        else:
            # continious solid beep 
            self.safe_kuksa_set(self.BUZZER_SIGNAL, 3)
            return 

        # Step 3: Non-blocking execution
        self.trigger_intermittent_buzzer(current_time, beep_interval, warning_level)