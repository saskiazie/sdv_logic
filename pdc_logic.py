import time
from kuksa_connection import KuksaConnection

class PDCLogic:
    '''
    Park Distance Control (PDC) and reverse backup light logic.

    Purpose:
        Activates the rear parking sensor and the backup light when the
        vehicle is in reverse with the engine running, and maps the
        measured obstacle distance to a dynamic warning beep.

    Input signals:
        Vehicle.Powertrain.Transmission.CurrentGear
        Vehicle.Powertrain.CombustionEngine.IsRunning
        Vehicle.ADAS.PDC.Rear.Distance (cm)

    Output signals:
        Vehicle.ADAS.PDC.Rear.IsActive
        Vehicle.Body.Lights.Backup.IsOn
        Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime
            (0 = silent, 1 = slow beep, 2 = rapid beep, 3 = solid beep)

    Notes:
        - The intermittent buzzer is a non-blocking pulse generator
          driven by elapsed time - no sleep() calls in the thread.
        - The buzzer signal is optional: writes go through
          safe_kuksa_publish() and are silently skipped if unmapped.
        - Deactivation publishes exactly once (guarded by pdc_active)
          to avoid signal and log spam.
    '''

    # Input signal paths
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"
    ENGINE_RUNNING_SIGNAL = "Vehicle.Powertrain.CombustionEngine.IsRunning"
    DISTANCE_SENSOR_SIGNAL = "Vehicle.ADAS.PDC.Rear.Distance"  # cm

    # Output signal paths
    PDC_REAR_ACTIVE_SIGNAL = "Vehicle.ADAS.PDC.Rear.IsActive"
    BACKUP_LIGHT_SIGNAL = "Vehicle.Body.Lights.Backup.IsOn"
    BUZZER_SIGNAL = "Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime"

    def __init__(self, kuksa: KuksaConnection, config, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state
        self.reverse_gear_threshold = config["reverse_gear_threshold"]

        # internal states
        self.pdc_active = False
        self.last_action_time = 0.0
        self.buzzer_toggle = False

    def is_reverse(self, gear):
        return gear < self.reverse_gear_threshold

    def safe_kuksa_publish(self, signal, value):
        '''publish a current value; silently skip if the signal is unmapped.'''
        try:
            self.kuksa.publish(signal, value)
        except Exception:
            pass

    def trigger_intermittent_buzzer(self, current_time, interval,
                                    active_level):
        '''Non-blocking pulse generator for the warning beep.'''
        if current_time - self.last_action_time >= interval:
            self.last_action_time = current_time
            self.buzzer_toggle = not self.buzzer_toggle

            # pulse the tone state based on the toggle
            target_value = active_level if self.buzzer_toggle else 0
            self.safe_kuksa_publish(self.BUZZER_SIGNAL, target_value)

    def run(self):
        if not self.vehicle_state.get("is_ready", False):
            return

        current_time = time.time()

        # read the current values from the broker
        try:
            gear = int(self.kuksa.get(self.GEAR_SIGNAL, 0))
            is_engine_running = bool(
                self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False))
            distance_cm = float(
                self.kuksa.get(self.DISTANCE_SENSOR_SIGNAL, 999.0))
        except Exception as e:
            print(f"[PDCLogic] Error: reading from broker failed: {e}")
            return

        # Step 1: system activation and backup light
        if is_engine_running and self.is_reverse(gear):
            if not self.pdc_active:
                self.kuksa.publish(self.BACKUP_LIGHT_SIGNAL, True)
                self.kuksa.publish(self.PDC_REAR_ACTIVE_SIGNAL, True)
                self.pdc_active = True
                print("[PDCLogic] Info: rear parking sensor and backup "
                      "light activated")
        else:
            # deactivate exactly once when leaving reverse operation
            if self.pdc_active:
                self.kuksa.publish(self.BACKUP_LIGHT_SIGNAL, False)
                self.kuksa.publish(self.PDC_REAR_ACTIVE_SIGNAL, False)
                self.safe_kuksa_publish(self.BUZZER_SIGNAL, 0)  # mute buzzer
                self.pdc_active = False
                self.buzzer_toggle = False
                print("[PDCLogic] Info: rear parking sensor and backup "
                      "light deactivated")
            return

        # Step 2: distance evaluation and mapping
        if distance_cm > 150.0:
            # out of warning range -> silence
            self.safe_kuksa_publish(self.BUZZER_SIGNAL, 0)
            self.buzzer_toggle = False
            return
        elif distance_cm > 100.0:
            beep_interval = 0.8   # slow beep
            warning_level = 1
        elif distance_cm > 50.0:
            beep_interval = 0.3   # rapid beep
            warning_level = 2
        else:
            # closer than 50 cm -> continuous solid beep
            self.safe_kuksa_publish(self.BUZZER_SIGNAL, 3)
            return

        # Step 3: non-blocking pulsed output
        self.trigger_intermittent_buzzer(current_time, beep_interval,
                                         warning_level)