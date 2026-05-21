class PDCLogic:

    # Input Signal
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"

    # Output Signal
    PDC_REAR_ACTIVE_SIGNAL = "Vehicle.ADAS.PDC.Rear.IsActive"

    def __init__(self, kuksa, config):
        self.kuksa = kuksa
        self.reverse_gear_threshold = config["reverse_gear_threshold"]
        self.pdc_active = False

    def is_reverse(self,gear):
        return gear < self.reverse_gear_threshold

    def run(self):

        # Read current values
        gear = int(self.kuksa.get(self.GEAR_SIGNAL, 0))

        # Activate rear PDC when reverse gear is selected
        if self.is_reverse(gear) and not self.pdc_active:
            self.kuksa.set(self.PDC_REAR_ACTIVE_SIGNAL, True)
            self.pdc_active = True
            print("PDC Info: Rear praking sensor activated")

        # Deactivate rear PDC when reverse gear is no longer selected
        elif not self.is_reverse(gear) and self.pdc_active:
            self.kuksa.set(self.PDC_REAR_ACTIVE_SIGNAL, False)
            self.pdc_active = False
            print("PDC Info: Rear praking sensor deactivated")