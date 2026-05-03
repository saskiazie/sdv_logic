class PowertrainSafetyLogic:

    # Input Signals
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"

    # Gear Values based on system definition 
    GEAR_NEUTRAL = 0
    GEAR_PARK = 126
    
    # Constructor 
    def __init__(self, kuksa):
        self.kuksa = kuksa
        self.last_valid_gear = self.GEAR_NEUTRAL
        self.last_warning = None
        self.last_valid_speed = 0

    def is_forward(self, gear): # check for forward driving state
        return gear > 0 or gear == 127

    def is_reverse(self, gear): # check for reverse driving state 
        return gear < 0
    
    def print_warning_once(self, warning_key, message): # for printing warning message only once per detection
        if self.last_warning != warning_key:
            print(message)
            self.last_warning = warning_key


    def run(self):
        # reading current values 
        speed = float(self.kuksa.get(self.SPEED_SIGNAL,0))
        gear = int(self.kuksa.get(self.GEAR_SIGNAL, self.GEAR_NEUTRAL))

## ---- Logic for invalid speed increase while in ivalid gear -------- 
        # Prevent Speed increase in invalid gear (N)
        if not (self.is_forward(gear) or self.is_reverse(gear)):
            # if speed increases while gear is invalid -> reset
            self.kuksa.publish(self.SPEED_SIGNAL, self.last_valid_speed)
            self.print_warning_once(
                "invalid_acceleration",
                "Safety: Acceleration not allowed in current gear, switch to Drive"
            )
        
        # Store last valid speed only if gear is valid
        if self.is_forward(gear) or self.is_reverse(gear):
            self.last_valid_speed = speed

## ---- Warnings for wanting to switch out of D while driving -----
        # Stores last valid gear 
        if self.is_forward(gear) or self.is_reverse(gear):
            self.last_valid_gear = gear

        # Prevention of switching gears to N or P while driving 
        if speed > 0 and gear == self.GEAR_PARK: # Prevent switching to parking while driving 
            #self.kuksa.publish(self.GEAR_SIGNAL, self.last_valid_gear)
            self.print_warning_once(
                "park_while_driving",
                "Safety warning: Park selected while driving not allowed"
            )
           
        elif speed > 0 and gear == self.GEAR_NEUTRAL:  # Prevent switching to neutral while driving 
            #self.kuksa.publish(self.GEAR_SIGNAL, self.last_valid_gear)
            self.print_warning_once(
                "neutral_while_driving",
                "Safety warning: Neutral selected while driving not allowed"
            )

        elif speed > 0 and not (self.is_forward(gear) or self.is_reverse(gear)): # General warning 
            self.print_warning_once(
                "invalid_gear",
                "Safety warning: Moving without valid gear"
            )
        else: # Reset state when the vehicle returns to a valid state
            self.last_warning = None    