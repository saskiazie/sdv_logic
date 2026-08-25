import time
from kuksa_connection import KuksaConnection

class LightsLogic:
    '''
    Controls the vehicle lighting based on the central vehicle state.

    Purpose:
        Provides lighting feedback for the access phases (unlock/lock)
        and activates the daytime running lights once the vehicle is
        ready. The startup decision itself is handled by StartSequence;
        this module only reacts to the vehicle_state flags.

    Input signals:
        vehicle_state["is_unlocked" | "is_ready" | "is_locked"]
        vehicle_state["hazard_enabled"]   (set by IndicatorLogic)

    Output signals:
        Vehicle.Body.Lights.LightSwitch                  (mode string)
        Vehicle.Cabin.Light.AmbientLight.IsLightOn       (interior)
        Vehicle.Body.Lights.Running.IsOn                 (DRL)
        Vehicle.Body.Lights.Beam.Low.IsOn                (reset on lock)
        Vehicle.Body.Lights.Hazard.IsSignaling           (feedback blink)
        Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime (lock buzzer)

    Notes:
        - The double-blink feedback is a non-blocking state machine
          driven by elapsed time - no sleep() calls in the thread.
        - While vehicle_state["hazard_enabled"] is True, the feedback
          machine keeps its hands off the hazard signal: the permanent
          hazard from IndicatorLogic always has priority.
        - The interior light switches off automatically after
          INTERIOR_LIGHT_TIMEOUT and publishes that exactly once.
    '''

    # Output signal paths
    LIGHT_SWITCH_SIGNAL = "Vehicle.Body.Lights.LightSwitch"
    INTERIOR_LIGHT_SIGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn"
    DAYTIME_RUNNING_LIGHT_SIGNAL = "Vehicle.Body.Lights.Running.IsOn"
    LOW_BEAM_SIGNAL = "Vehicle.Body.Lights.Beam.Low.IsOn"
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"
    LEFT_LIGHT_SIGNAL = (
        "Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling")
    RIGHT_LIGHT_SIGNAL = (
        "Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling")

    # Acoustic signal
    BUZZER_SIGNAL = "Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime"

    # Timing configuration (seconds)
    INTERIOR_LIGHT_TIMEOUT = 5.0
    BUZZER_TIMEOUT = 0.2

    def __init__(self, kuksa: KuksaConnection, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        # one-shot flags per phase
        self.unlock_feedback_done = False
        self.lock_feedback_done = False
        self.ready_lighting_done = False

        # double-blink state machine
        self.feedback_active = False
        self.feedback_start_time = 0.0
        self.feedback_step = 0

        # interior light timer
        self.interior_light_start_time = None

        # buzzer timer
        self.buzzer_active = False
        self.buzzer_start_time = 0.0

    def set_feedback_lights(self, state):
        '''Sets hazard AND both indicator lights in one atomic call.

        The double blink must drive all three IsSignaling signals:
        in Unreal the SetTurnLeft/Right events run after SetHazard
        in the same frame and would otherwise overwrite the blinker
        materials with their (false) idle state.
        '''
        self.kuksa.write_many({
            self.HAZARD_SIGNAL: state,
            self.LEFT_LIGHT_SIGNAL: state,
            self.RIGHT_LIGHT_SIGNAL: state,
        })

    def handle_double_blink(self, current_time):
        '''Two short hazard flashes as unlock/lock feedback.'''
        if self.vehicle_state.get("hazard_enabled", False):
            return  # permanent hazard active - IndicatorLogic owns the signal
        if not self.feedback_active:
            return

        elapsed = current_time - self.feedback_start_time

        # first flash on (0.0 - 0.3 s)
        if elapsed < 0.3 and self.feedback_step == 0:
            self.set_feedback_lights(True)
            self.feedback_step = 1

        # first flash off (0.3 - 0.6 s)
        elif 0.3 <= elapsed < 0.6 and self.feedback_step == 1:
            self.set_feedback_lights(False)
            self.feedback_step = 2

        # second flash on (0.6 - 0.9 s)
        elif 0.6 <= elapsed < 0.9 and self.feedback_step == 2:
            self.set_feedback_lights(True)
            self.feedback_step = 3

        # second flash off (0.9 - 1.2 s)
        elif 0.9 <= elapsed < 1.2 and self.feedback_step == 3:
            self.set_feedback_lights(False)
            self.feedback_step = 4

        # end condition: make sure the light is off, stop the machine
        elif elapsed >= 1.2:
            self.set_feedback_lights(False)
            self.feedback_active = False

    def handle_buzzer_timeout(self, current_time):
        '''Switches the lock confirmation buzzer off after its timeout.'''
        if not self.buzzer_active:
            return

        if current_time - self.buzzer_start_time >= self.BUZZER_TIMEOUT:
            try:
                self.kuksa.write(self.BUZZER_SIGNAL, 0)
            except Exception:
                pass  # buzzer signal is optional (may not be mapped)
            self.buzzer_active = False

    def handle_unlock(self, current_time):
        '''Welcome feedback: interior light on + double blink.'''
        if not self.unlock_feedback_done:
            # vehicle still in access phase -> main switch off
            self.kuksa.write(self.LIGHT_SWITCH_SIGNAL, "OFF")

            # interior light on, with auto-off timer
            self.kuksa.write(self.INTERIOR_LIGHT_SIGNAL, True)
            self.interior_light_start_time = current_time

            # start the double-blink sequence
            self.feedback_active = True
            self.feedback_start_time = current_time
            self.feedback_step = 0

            self.unlock_feedback_done = True
            self.lock_feedback_done = False

            print("[LightsLogic] Info: unlock feedback activated")

        # automatically switch off the interior light (publish once)
        if (self.interior_light_start_time
                and current_time - self.interior_light_start_time
                >= self.INTERIOR_LIGHT_TIMEOUT):
            self.kuksa.write(self.INTERIOR_LIGHT_SIGNAL, False)
            self.interior_light_start_time = None

    def handle_ready(self):
        '''Driving lights once the vehicle reports ready.'''
        if self.ready_lighting_done:
            return

        # activate DRL via the VSS light switch + the light itself
        self.kuksa.write(self.LIGHT_SWITCH_SIGNAL, "DAYTIME_RUNNING_LIGHTS")
        self.kuksa.write(self.DAYTIME_RUNNING_LIGHT_SIGNAL, True)

        # disable the welcome lighting
        self.kuksa.write(self.INTERIOR_LIGHT_SIGNAL, False)

        self.ready_lighting_done = True
        print("[LightsLogic] Info: daytime running lights activated")

    def handle_lock(self, current_time):
        '''Goodbye feedback: all lights off + double blink + buzzer.'''
        if self.lock_feedback_done:
            return

        # main light switch off, exterior and interior lights off
        self.kuksa.write(self.LIGHT_SWITCH_SIGNAL, "OFF")
        self.kuksa.write(self.DAYTIME_RUNNING_LIGHT_SIGNAL, False)
        self.kuksa.write(self.LOW_BEAM_SIGNAL, False)
        self.kuksa.write(self.INTERIOR_LIGHT_SIGNAL, False)

        # start the double-blink sequence
        self.feedback_active = True
        self.feedback_start_time = current_time
        self.feedback_step = 0

        # optional acoustic lock confirmation
        try:
            self.kuksa.write(self.BUZZER_SIGNAL, 1)
            self.buzzer_active = True
            self.buzzer_start_time = current_time
        except Exception:
            pass  # buzzer signal is optional (may not be mapped)

        self.lock_feedback_done = True
        self.unlock_feedback_done = False
        self.ready_lighting_done = False

        print("[LightsLogic] Info: lock feedback activated")

    def run(self):
        current_time = time.time()

        # time-driven state machines run every cycle
        self.handle_double_blink(current_time)
        self.handle_buzzer_timeout(current_time)

        # phase handlers react to the central vehicle state
        if self.vehicle_state.get("is_unlocked", False):
            self.handle_unlock(current_time)

        if self.vehicle_state.get("is_ready", False):
            self.handle_ready()

        if self.vehicle_state.get("is_locked", False):
            self.handle_lock(current_time)