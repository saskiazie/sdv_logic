import time # for waiting time

class StartSequence:
# PassengerSide = Unlock Request -> Unlock detected + Hazard Lights twice + Interior Light # temporary access signal
# DriverSide = Door open -> Access granted 

    # Input signals
    # Trigger Unlock SDV with opening PassengerSide Row1
    UNLOCK_REQUEST_SIGNAL = "Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen" # temporary test trigger until keyless event available 
    DOOR_OPEN_SIGNAL = "Vehicle.Cabin.Door.Row1.DriverSide.IsOpen"

    # Output signals
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"
    INTERIOR_LIGHT_SIGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn" #"Vehicle.Cabin.Light.AmbientLight.Row2.DriverSide.IsLightOn" 

    def __init__(self, kuksa):
        self.kuksa = kuksa
        self.unlock_done = False
        self.last_door_open = False

    # Function Defintition for Blink hazard light twice
    def blink_hazard_twice(self):
        for _ in range(2):
            self.kuksa.set(self.HAZARD_SIGNAL, True)
            time.sleep(0.4)
            self.kuksa.set(self.HAZARD_SIGNAL, False)
            time.sleep(0.4)

    def run(self):
        unlock_request = bool(self.kuksa.get(self.UNLOCK_REQUEST_SIGNAL, False))
        door_open = bool(self.kuksa.get(self.DOOR_OPEN_SIGNAL, False))

        # Unlock detected 
        if unlock_request is True and not self.unlock_done:
            print("Unlock detected")

            # Blink hazard lights twice
            self.blink_hazard_twice()

            # Turn on interior light (ambient light)
            self.kuksa.set(self.INTERIOR_LIGHT_SIGNAL, True)

            self.unlock_done = True

        # Driver door opened 
        if door_open is True and not self.last_door_open and self.unlock_done:
            print("Driver door opened --> Access granted") 

        # Saving last state
        self.last_door_open = door_open    