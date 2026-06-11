class LightsLogic:
    # Input Signals
    UNLOCK_REQUEST_SIGNAL = "Vehicle.Body.Access.KeyFob.UnlockRequest"
    DRIVER_DOOR_SIGNAL = "Vehicle.Cabin.Door.Row1.DriverSide.IsLocked"
    
    
    IGNITION_SIGNAL = "Vehicle.Body.Access.KeyFob.IgnitionRequst" # platzhalter "Vehicle.LowVoltageSystemState"

    DAYTIME_RUNNING_LIGHT_SIGNAL = "Vehicle.Body.Lights.Running.IsOn"
    LOW_BEAM_SIGNAL = "Vehicle.Body.Lights.Beam.Low.IsOn"

    def __init__(self, kuksa, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state
        self.lights_active = False

    def run(self):
        if not self.vehicle_state.get("is_ready", False):
            return
        
        ignition_state = str(self.kuksa.get(self.IGNITION_SIGNAL, "LOCK"))

        if ignition_state == "ON" and not self.lights_active:
            self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, True)
            self.lights_active = True
            print("Lights Info: Daytime running lights activted")

        elif ignition_state in ["LOCK", "OFF"] and self.lights_active:
            self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, False)
            self.kuksa.publish(self.LOW_BEAM_SIGNAL, False)
            self.lights_active = False
            print("Lights Info: Vehicle lights deactivated")    
