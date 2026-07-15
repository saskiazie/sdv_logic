import time
from kuksa_connection import KuksaConnection

class IndicatorLogic:
    '''
    Central turn indicator and hazard light logic.

    Purpose:
        Translates driver intent (switch signals) into blinking light
        states at the legally required frequency. 

    Input signals:
        Vehicle.Body.Lights.Hazard.IsEnabled (switch)
        Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled (switch)
        Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled (switch)

    Output signals:
        Vehicle.Body.Lights.Hazard.IsSignaling (light)
        Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling (light)
        Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling (light)
        vehicle_state["hazard_enabled"]   (internal flag for LightsLogic)

    Notes:
        - Blink frequency is 1.5 Hz (90 flashes/min).
        - Hazard has priority over the individual indicators. Design
          decision (step 1a): releasing the hazard switch also clears
          any engaged individual indicator - "hazard off = everything off" behavior.
        - Left/right interlock happens on switch level (step 1b): a
          freshly pressed switch wins and releases the opposite one.
          Both switches at once are only legal via hazard.
        - Active channels publish their target state EVERY cycle and
          all updates go out in ONE atomic publish_many() call: a lost
          or delayed publish heals within one cycle, and left/right
          can never drift apart. Designed for the 0.02 s fast lane.
        - Hazard must work even if the vehicle is off (no ignition required), 
          therefore its not dependant on the vehicle_state["is_ready"] flag.
    '''

    # Input: switch signals (driver intent, constant true/false) - New signals 
    HAZARD_SWITCH = "Vehicle.Body.Lights.Hazard.IsEnabled"
    LEFT_SWITCH = "Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled"
    RIGHT_SWITCH = "Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled"

    # Output: light state signals (toggled while enabled)
    HAZARD_LIGHT = "Vehicle.Body.Lights.Hazard.IsSignaling"
    LEFT_LIGHT = "Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling"
    RIGHT_LIGHT = "Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling"

    # Phase duration in seconds (one ON or one OFF phase).
    # Full blink period = 2 x BLINK_PERIOD -> 0.667 s -> 1.5 Hz.
    BLINK_PERIOD = 0.333

    def __init__(self, kuksa: KuksaConnection, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        self.blink_state = False   # shared clock: True = lights-on phase
        self.last_toggle = 0.0

        # per-channel request state of the PREVIOUS cycle
        # (needed to detect a channel switching off, see step 5)
        self.prev_request = {
            self.HAZARD_LIGHT: False,
            self.LEFT_LIGHT: False,
            self.RIGHT_LIGHT: False,
        }

        # previous switch states (edge detection for steps 1a and 1b)
        self.prev_left_switch = False
        self.prev_right_switch = False
        self.prev_hazard_switch = False

    def run(self):
        # 1. Read all three switch signals in one gRPC call
        try:
            vals = self.kuksa.get_many([self.HAZARD_SWITCH, self.LEFT_SWITCH, self.RIGHT_SWITCH])
            hazard_on = bool(vals[self.HAZARD_SWITCH] or False)
            left_on = bool(vals[self.LEFT_SWITCH] or False)
            right_on = bool(vals[self.RIGHT_SWITCH] or False)
        except Exception as e:
            print(f"[IndicatorLogic] Error: reading switches failed: {e}")
            return

        # 1a. Hazard falling edge: releasing the hazard switch also
        # releases any engaged individual indicator (design decision,
        # see docstring - deviates from a mechanically latched stalk).
        if self.prev_hazard_switch and not hazard_on:
            if left_on:
                left_on = False
                self.kuksa.publish(self.LEFT_SWITCH, False)
            if right_on:
                right_on = False
                self.kuksa.publish(self.RIGHT_SWITCH, False)
            print("[IndicatorLogic] Info: hazard released -> "
                  "individual indicators cleared")
        self.prev_hazard_switch = hazard_on

        # 1b. Left/right interlock (individual indicators only, hazard
        # is a separate switch and exempt from this rule): a freshly
        # pressed switch wins and releases the opposite one 
        if left_on and right_on and not hazard_on:
            left_is_new = left_on and not self.prev_left_switch
            right_is_new = right_on and not self.prev_right_switch

            if left_is_new and not right_is_new:
                right_on = False
                self.kuksa.publish(self.RIGHT_SWITCH, False)
                print("[IndicatorLogic] Info: left engaged -> "
                      "right released")
            else:
                # right freshly pressed (or undecidable) -> right wins
                left_on = False
                self.kuksa.publish(self.LEFT_SWITCH, False)
                print("[IndicatorLogic] Info: right engaged -> "
                      "left released")

        # remember switch states for next cycle's edge detection
        self.prev_left_switch = left_on
        self.prev_right_switch = right_on

        # 2. Priority: hazard overrides the individual indicators
        if hazard_on:
            left_on = True
            right_on = True

        # Tell LightsLogic to keep its hands off the hazard signal
        self.vehicle_state["hazard_enabled"] = hazard_on

        # 3. Truth table for this cycle: which channel shall blink now
        request = {
            self.HAZARD_LIGHT: hazard_on,
            self.LEFT_LIGHT: left_on,
            self.RIGHT_LIGHT: right_on,
        }

        any_active = any(request.values())
        was_any_active = any(self.prev_request.values())
        now = time.time()

        # 4. Shared blink clock (all active channels blink in sync)
        if any_active:
            if not was_any_active:
                # first activation: start with the ON phase, reset clock
                self.blink_state = True
                self.last_toggle = now
            elif now - self.last_toggle >= self.BLINK_PERIOD:
                self.blink_state = not self.blink_state
                self.last_toggle += self.BLINK_PERIOD
                # catch-up guard: after a thread stall resync instead
                # of burst-toggling
                if now - self.last_toggle >= self.BLINK_PERIOD:
                    self.last_toggle = now

        # 5. Collect all channel states, then publish them in ONE call. Left/right can 
        # never drift apart: they always
        # land in the same write.
        updates = {}
        for signal, is_requested in request.items():
            if is_requested:
                updates[signal] = self.blink_state
            elif self.prev_request[signal]:
                # channel just switched off -> force the light off once
                updates[signal] = False

        if updates:
            self.kuksa.publish_many(updates)

        self.prev_request = request