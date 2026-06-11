
class AutoLock:
    '''
    Handles the speed-dependant automatic door looking logic
    - Automatically locks all doors once the vehicle exceeds a configured speed threshold (imported from yaml file)
    - Prevents doors from being opened while the vehicle is moving 
    '''

    # Input Signals
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"
    GEAR_PARK = 126
    GEAR_NEUTRAL = 0

    # Output Signals
    DRIVER_LOCK = "Vehicle.Cabin.Door.Row1.DriverSide.IsOpen"
    PASSENGER_LOCK = "Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen"



    # Constructor (kuksa connection, speed threshold in km/h for automatic locking)   
    def __init__(self, kuksa, config, vehicle_state): # werte als konstanten zuweisen (kennen den namen und lesen werte ein) NEU
        self.kuksa = kuksa
        self.threshold = config["threshold_kmh"]
        self.vehicle_state = vehicle_state

        # Internal state to prevent repeated locking elements 
        self.auto_locked = False
        self.door_warning_active = False

    # Function for combining all available doors (extendable)
    # value = False -> doors closed
    # value = True -> doors open
    def lock_all_doors(self, value):
        self.kuksa.set(self.DRIVER_LOCK, value)
        self.kuksa.set(self.PASSENGER_LOCK, value)

    # Executes the speed-dependant lockign logic
    def run(self):
        
        if not self.vehicle_state.get("is_ready", False):
            return

        # Reading Vehicle Speed from kuksa
        try:
            speed = float(self.kuksa.get(self.SPEED_SIGNAL, 0))
            driver_door = bool(self.kuksa.get(self.DRIVER_LOCK, False))
            passenger_door = bool(self.kuksa.get(self.PASSENGER_LOCK, False))
            gear = int(self.kuksa.get(self.GEAR_SIGNAL, self.GEAR_PARK))

        except Exception as e:
            print("Autolock Error: Failed to fetch data from Broker: {e}")
            return 

        # Lock logic: if speed exceeds the threshold and car is not already locked - lock doors 
        if speed > self.threshold and gear not in [self.GEAR_PARK, self.GEAR_NEUTRAL]:
            
            # Initial automatic lock when passing speed limit
            if not self.auto_locked:
                self.lock_all_doors(False)
                self.auto_locked = True
                print(f"Auto-Lock Info: Target speed exceeded {speed} km/h -> All doors locked") # testing in terminal
            
            # Permanent protection override 
            # if any doors interface reports an open state while moving, overrid eit instantly 
            elif driver_door is True or passenger_door is True:
                self.lock_all_doors(False)

                if not self.door_warning_active:
                    print(f"Autolock Safety Warning: Door opening attempt blocked while moving at {speed} km/h")
                    self.door_warning_active = True
        else:
            # Reset trigger flag once the vehicle drops below the threshold         
            if self.auto_locked:
                print("Autolock Info: Vehicle stopped or below threshold -> Autolock disarmed")
                self.auto_locked = False 

            self.door_warning_active = False    