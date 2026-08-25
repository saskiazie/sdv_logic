from kuksa_connection import KuksaConnection

class PowertrainSafetyLogic:
    '''
    Safety rules for the vehicle powertrain.

    Purpose:
        Validates the gear selection against the current motion state.
        Invalid gear changes while moving (Park/Neutral) are corrected
        by restoring the last valid driving gear; states that cannot be
        corrected are reported with a warning.

    Input signals:
        Vehicle.Speed
        Vehicle.Powertrain.Transmission.CurrentGear

    Output signals:
        Vehicle.Powertrain.Transmission.CurrentGear  (corrections only)

    Notes:
        - Design decision: this module NEVER writes Vehicle.Speed.
          Speed is a sensor value owned by the speed source. 
          A logic module overwriting a
          sensor would create two competing sources of truth and fight
          the real source every cycle. Invalid acceleration is
          therefore warned about, but not "corrected".
        - Gear semantics (VSS custom mapping): gear < 0 = reverse,
          0 = neutral, 126 = park, 127 = drive. All codes and
          thresholds come from the powertrain config section.
        - Warnings are printed once per condition (no log spam) and
          re-armed when the vehicle returns to a valid state.
    '''

    # Input signal paths
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"

    def __init__(self, kuksa: KuksaConnection, config, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        # gear codes and thresholds from the powertrain config section
        self.gear_neutral = config["gear_neutral"]
        self.gear_park = config["gear_park"]
        self.gear_drive = config["gear_drive"]
        self.reverse_gear_threshold = config["reverse_gear_threshold"]
        self.moving_speed_threshold = config["moving_speed_threshold_kmh"]

        # runtime state
        self.last_valid_gear = self.gear_park
        self.last_warning = None

    def is_forward(self, gear):
        return gear == self.gear_drive

    def is_reverse(self, gear):
        return gear < self.reverse_gear_threshold

    def is_driving_gear(self, gear):
        return self.is_forward(gear) or self.is_reverse(gear)

    def print_warning_once(self, warning_key, message):
        '''Prints a warning only once until the condition changes.'''
        if self.last_warning != warning_key:
            print(message)
            self.last_warning = warning_key

    def run(self):
        if not self.vehicle_state.get("is_ready", False):
            return

        # read the current motion state from the broker
        try:
            speed = float(self.kuksa.get(self.SPEED_SIGNAL, 0))
            gear = int(self.kuksa.get(self.GEAR_SIGNAL, self.gear_neutral))
        except Exception as e:
            print(f"[PowertrainSafety] Error: reading from broker "
                  f"failed: {e}")
            return

        # remember the last driving gear for later corrections
        if self.is_driving_gear(gear):
            self.last_valid_gear = gear

        moving = speed > self.moving_speed_threshold

        # Deliberately publish(), not write(): CurrentGear is of type
        # sensor. On the wired demonstrator the transmission owns it and
        # would overwrite the correction - see writemode_config.yaml.
        # Case 1: Park selected while moving
        if moving and gear == self.gear_park:
            if self.is_driving_gear(self.last_valid_gear):
                # driver shifted to Park while driving -> restore gear
                self.kuksa.publish(self.GEAR_SIGNAL, self.last_valid_gear)
                self.print_warning_once(
                    "park_while_driving",
                    "[PowertrainSafety] Warning: shift to Park while "
                    "moving blocked - gear restored")
            else:
                # vehicle "moves" although it never left Park: the speed
                # source ignores the gear. Cannot be corrected without
                # writing Vehicle.Speed -> warn.
                self.print_warning_once(
                    "moving_in_park",
                    "[PowertrainSafety] Warning: speed > 0 while in "
                    "Park - acceleration in Park is not allowed")

        # Case 2: Neutral selected while moving
        elif moving and gear == self.gear_neutral:
            if self.is_driving_gear(self.last_valid_gear):
                self.kuksa.publish(self.GEAR_SIGNAL, self.last_valid_gear)
                self.print_warning_once(
                    "neutral_while_driving",
                    "[PowertrainSafety] Warning: shift to Neutral while "
                    "moving blocked - gear restored")
            else:
                self.print_warning_once(
                    "moving_in_neutral",
                    "[PowertrainSafety] Warning: speed > 0 while in "
                    "Neutral - acceleration in Neutral is not allowed")

        # Case 3: moving in any other non-driving gear
        elif moving and not self.is_driving_gear(gear):
            self.print_warning_once(
                "invalid_gear",
                "[PowertrainSafety] Warning: moving without a valid gear")

        # Valid state again -> re-arm the warnings
        else:
            self.last_warning = None