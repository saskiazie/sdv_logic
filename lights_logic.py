import time

class LightsLogic:

    '''
    Controls vehicle lightning based on the central vehicle state
    - React to th eunlock state 
    - Control the VSS main light switch 
    - activate interior light and harźard feedback after unlock and lock 
    - activate daytim erunning lights after ready
    - reset lightning when vehicle is no longer active
    - startp decision is handled by StartSequence
 
    '''
    
    # Light Switch 
    LIGHT_SWITCH_SIGNAL = "Vehicle.Body.Lights.LightSwitch"

    # Light outputs
    INTERIOR_LIGHT_SIGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn"
    DAYTIME_RUNNING_LIGHT_SIGNAL = "Vehicle.Body.Lights.Running.IsOn"
    LOW_BEAM_SIGNAL = "Vehicle.Body.Lights.Beam.Low.IsOn"
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"

    # acoustic signal
    BUZZER_SIGNAL = "Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime"

    # Timing configuration 
    INTERIOR_LIGHT_TIMEOUT = 5.0
    BUZZER_TIMEOUT = 0.2

    def __init__(self, kuksa, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        self.unlock_feedback_done = False
        self.lock_feedback_done = False
        self.ready_lighting_done = False

        # double blink state machine 
        self.feedback_active = False
        self.feedback_start_time = 0.0
        self.feedback_step = 0

        # Interior light timer 
        self.interior_light_start_time = None

        # Buzzer timer
        self.buzzer_active = False
        self.buzzer_start_time = 0.0

    # main loop
    def run(self):
        current_time = time.time()

        self.handle_double_blink(current_time)
        self.handle_buzzer_timeout(current_time)

        if self.vehicle_state.get("is_unlocked", False):
            self.handle_unlock(current_time)    

        if self.vehicle_state.get("is_ready", False):
            self.handle_ready()

        if self.vehicle_state.get("is_locked", False):
            self.handle_lock(current_time)

   
   # double blink hazard lights
    def handle_double_blink(self, current_time):
        if not self.feedback_active:
            return 

        elapsed = current_time - self.feedback_start_time

        # first blink on                 
        if elapsed < 0.3 and self.feedback_step == 0:
            self.kuksa.publish(self.HAZARD_SIGNAL, True)
            self.feedback_step = 1

        # first blink off  
        elif 0.3 <= elapsed < 0.6 and self.feedback_step == 1:
            self.kuksa.publish(self.HAZARD_SIGNAL, False)
            self.feedback_step = 2
        
        # second blink on 
        if 0.6 <= elapsed < 0.9 and self.feedback_step == 2:
            self.kuksa.publish(self.HAZARD_SIGNAL, True)
            self.feedback_step = 3

        # second blink: turn off (1.2 to 1.6 sec)    
        elif 0.9 <= elapsed < 1.2 and self.feedback_step == 3:
            self.kuksa.publish(self.HAZARD_SIGNAL, False)
            self.feedback_step = 4

        # End condition
        elif elapsed >= 1.2:
            self.kuksa.publish(self.HAZARD_SIGNAL, False)
            self.feedback_active = False # Deactivate blink state machine 


    # buzzer timer
    def handle_buzzer_timeout(self, current_time):
        if not self.buzzer_active:
            return

        elapsed = current_time - self.buzzer_start_time

        if elapsed >= self.BUZZER_TIMEOUT:
            try:
                self.kuksa.publish(self.BUZZER_SIGNAL, 0)
            except Exception:
                pass

            self.buzzer_active = False


    # unlock feedback 
    def handle_unlock(self, current_time):
        if not self.unlock_feedback_done:

            # Vehicle still in access phase
            self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "OFF")

            # Interior light ON
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, True)

            # Start double blink sequence
            self.feedback_active = True
            self.feedback_start_time = current_time
            self.feedback_step = 0

            self.interior_light_start_time = current_time

            self.unlock_feedback_done = True
            self.lock_feedback_done = False

            print("Lights Info: Unlock feedback activated")

        # Automatically switch off interior light
        if (self.interior_light_start_time and current_time - self.interior_light_start_time >= self.INTERIOR_LIGHT_TIMEOUT):
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)

    # Ready state

    def handle_ready(self):
        if self.ready_lighting_done:
            return

        # Activate DRL via VSS light switch
        self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "DAYTIME_RUNNING_LIGHTS")

        self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, True)

        # Disable welcome lighting
        self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)

        self.ready_lighting_done = True

        print("Lights Info: Daytime running lights activated")


    # lock feedback

    def handle_lock(self, current_time):
        if self.lock_feedback_done:
            return

        # Main light switch OFF
        self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "OFF")

        # Disable exterior lights
        self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, False)

        self.kuksa.publish(self.LOW_BEAM_SIGNAL, False)

        # Disable interior light
        self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)

        # Start double blink sequence
        self.feedback_active = True
        self.feedback_start_time = current_time
        self.feedback_step = 0

        # Optional acoustic lock confirmation
        try:
            self.kuksa.publish(self.BUZZER_SIGNAL, 1)

            self.buzzer_active = True
            self.buzzer_start_time = current_time

        except Exception:
            pass

        self.lock_feedback_done = True
        self.unlock_feedback_done = False
        self.ready_lighting_done = False

        print( "Lights Info: Lock feedback activated" )


'''

        # internal state flags
        self.unlock_lightning_done = False
        self.ready_lighting_done = False
        self.lock_feedback_done = False

        # non blocking timers 
        self.unlock_feedback_start_time = None
        self.lock_feedback_start_time = None

        # Timing configuration
        self.unlock_light_duration = 3.0
        self.lock_light_duration = 2.0
        self.hazard_feedback_duration = 1.0
        self.buzzer_feedback_duration = 0.2

    def run(self):
        current_time = time.time()

        if self.vehicle_state.get("is_unlocked", False):
            self._handle_unlock_lightning(current_time)

        if self.vehicle_state.get("is_ready", False):
            self._handle_ready_lightning()

        if self.vehicle_state.get("is_locked", False):
            self._handle_lock_feedback(current_time)

    def _handle_unlock_lightning(self, current_time):
        if not self.unlock_lightning_done:
            self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "OFF")
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, True)
            self.kuksa.publish(self.HAZARD_SIGNAL, True)

            self.unlock_feedback_start_time = current_time
            self.unlock_lightning_done = True
            self.lock_feedback_done = False

            print("Lights Info: Unlock feedback detected")

        elapsed = current_time - self.unlock_feedback_start_time

        if elapsed >= self.hazard_feedback_duration:
            self.kuksa.publish(self.HAZARD_SIGNAL, False)

        if elapsed >= self.unlock_light_duration:
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)

    def _handle_ready_lightning(self):
        if self.ready_lighting_done:
            return 

        self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "DAYTIME_RUNNING_LIGHTS")

        self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, True)
        self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)
        self.kuksa.publish(self.HAZARD_SIGNAL, False)              

        self.ready_lighting_done = True
        print("Lights Info: READY lightning activated")

    def _handle_lock_feedback(self, current_time):
        if not self.lock_feedback_done:
            self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "OFF")

            # Lock confirmation feedback 
            self.kuksa.publish(self.HAZARD_SIGNAL, True)
            self.kuksa.publish(self.BUZZER_SIGNAL, 3)

            # vehicle is closed, so interior light must be off
            self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)

            # exterior driving lights off
            self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, False)
            self.kuksa.publish(self.LOW_BEAM_SIGNAL, False)

            self.lock_feedback_start_time = current_time
            self.lock_feedback_done = True

            # reset unlock / ready light states 
            self.unlock_lightning_done = False
            self.ready_lighting_done = False

            print("Lights Info: Lock feedback activated")

        elapsed = current_time - self.lock_feedback_start_time

        if elapsed >= self.buzzer_feedback_duration:
            self.kuksa.publish(self.BUZZER_SIGNAL, 0)                                                     

        if elapsed >= self.lock_light_duration:
            self.kuksa.publish(self.HAZARD_SIGNAL, False)       

    def reset_lights(self):
        self.kuksa.publish(self.LIGHT_SWITCH_SIGNAL, "OFF")
        self.kuksa.publish(self.DAYTIME_RUNNING_LIGHT_SIGNAL, False)
        self.kuksa.publish(self.LOW_BEAM_SIGNAL, False)
        self.kuksa.publish(self.INTERIOR_LIGHT_SIGNAL, False)
        self.kuksa.publish(self.HAZARD_SIGNAL, False)
        self.kuksa.publish(self.BUZZER_SIGNAL, False)                        

        self.unlock_lightning_done = False
        self.ready_lightning_done = False
        self.lock_feedback_done = False

        self.unlock_feedback_start_time = None
        self.lock_feedback_start_time = None

        print("Lights Info: Lightning system reset")                                                                                   

'''