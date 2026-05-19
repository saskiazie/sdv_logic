
class AutoLock:
# Speed dependant Locking of Doors
    # Input Signals
    SPEED_SIGNAL = "Vehicle.Speed"

    # Output Signals
    DRIVER_LOCK = "Vehicle.Cabin.Door.Row1.DriverSide.IsOpen"
    PASSENGER_LOCK = "Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen"


    # Constructor (kuksa connection, speed threshold in km/h for automatic locking) 
    # -> lieber konstante un ddann initiator der alle konstanten befüllt (zB yaml file -> ein ezentrale kofig datei oder mehrere)
    # zB alle config.yml dateien werden reingeladen NEU
    
    def __init__(self, kuksa, config): # werte als konstanten zuweisen (kennen den namen und lesen werte ein) NEU
        self.kuksa = kuksa
        self.threshold = config["threshold"]

        # Internal state to prevent repeated locking elements 
        self.auto_locked = False

    # Function for combining all available doors (extendable)
    # value = False -> doors closed
    # value = True -> doors open
    def lock_all_doors(self, value):
        self.kuksa.set(self.DRIVER_LOCK, value)
        self.kuksa.set(self.PASSENGER_LOCK, value)

    # Executes the speed-dependant lockign logic
    def run(self):
        # Reading Vehicle Speed from kuksa
        speed = float(self.kuksa.get(self.SPEED_SIGNAL, 0))

        # Lock logic: if speed exceeds the threshold and car is not already locked - lock doors 
        if speed > self.threshold and not self.auto_locked:
            self.lock_all_doors(False)
            self.auto_locked = True
            print(f"Auto-Lock activated at {speed} km/h") # testing in terminal

        # if speed is below threshold reset internal state (for locking again)
        elif speed <= self.threshold:
            self.auto_locked = False