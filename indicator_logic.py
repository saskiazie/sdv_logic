import time

class IndicatorLogic:
    '''
    Central turn indicator / hazard blinking logic 
    - Reads driver intent from the IsEnabled switch signals (constant true/false)
    - Toggles the IsSignaling light-state signals at 1.5 Hz while enabled
      (1.5 Hz = legally required indicator frequency, StVZO)
    - Hazard has priority over left/right indicators
    - Publishes a vehicle_state flag so LightsLogic feedback sequences
      do not interfere while hazard is enabled
    '''

    # Input: switch signals (driver intent)
    HAZARD_SWITCH = "Vehicle.Body.Lights.Hazard.IsEnabled"
    LEFT_SWITCH = "Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled"
    RIGHT_SWITCH = "Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled"

    # Output: light state signals (toggled)
    HAZARD_LIGHT = "Vehicle.Body.Lights.Hazard.IsSignaling"
    LEFT_LIGHT = "Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling"
    RIGHT_LIGHT = "Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling"

    BLINK_PERIOD = 0.4  # seconds per phase -> 1.5 Hz

    def __init__(self, kuksa, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        self.blink_state = False
        self.last_toggle = 0.0
        self.was_active = False

    def run(self):
        # 1. Read all three switches in one gRPC call (fast lane friendly)
        try:
            vals = self.kuksa.get_many(
                [self.HAZARD_SWITCH, self.LEFT_SWITCH, self.RIGHT_SWITCH]
            )
            hazard_on = bool(vals[self.HAZARD_SWITCH] or False)
            left_on = bool(vals[self.LEFT_SWITCH] or False)
            right_on = bool(vals[self.RIGHT_SWITCH] or False)
        except Exception as e:
            print(f"IndicatorLogic Error while reading switches: {e}")
            return

        # 2. Priority: hazard overrides individual indicators
        if hazard_on:
            left_on = True
            right_on = True

        # Tell LightsLogic to keep its hands off the hazard signal
        self.vehicle_state["hazard_enabled"] = hazard_on

        active = left_on or right_on
        now = time.time()

        # 3. Toggle at 1.5 Hz while any indicator is requested
        if active:
          
            if not self.was_active:
                self.blink_state = True
                self.last_toggle = now
                self.kuksa.publish(self.HAZARD_LIGHT, True) if hazard_on else None
                if left_on:
                    self.kuksa.publish(self.LEFT_LIGHT, True)
                if right_on:
                    self.kuksa.publish(self.RIGHT_LIGHT, True)

            elif now - self.last_toggle >= self.BLINK_PERIOD:
                self.blink_state = not self.blink_state
                self.last_toggle += self.BLINK_PERIOD

                if now - self.last_toggle >= self.BLINK_PERIOD:
                    self.last_toggle = now

                if hazard_on:
                    self.kuksa.publish(self.HAZARD_LIGHT, self.blink_state)
                if left_on:
                    self.kuksa.publish(self.LEFT_LIGHT, self.blink_state)
                if right_on:
                    self.kuksa.publish(self.RIGHT_LIGHT, self.blink_state)

        elif self.was_active:
            self.kuksa.publish(self.HAZARD_LIGHT, False)
            self.kuksa.publish(self.LEFT_LIGHT, False)
            self.kuksa.publish(self.RIGHT_LIGHT, False)
            self.blink_state = False            
            
        self.was_active = active