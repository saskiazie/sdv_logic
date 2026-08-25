from kuksa_connection import KuksaConnection

class AutoLock:
    '''
    Speed-dependent automatic door locking.

    Purpose:
        Locks all doors once the vehicle exceeds a configured speed
        threshold and keeps them locked while the vehicle is moving.

    Input signals:
        Vehicle.Speed
        Vehicle.Powertrain.Transmission.CurrentGear
        Vehicle.Cabin.Door.Row1.DriverSide.IsLocked (read back)
        Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked (read back)

    Output signals:
        Vehicle.Cabin.Door.Row1.DriverSide.IsLocked
        Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked
            (True = locked, False = unlocked)

    Notes:
        - Inactive until the start sequence sets vehicle_state["is_ready"].
        - While moving, any unlock attempt is overridden immediately
          (permanent protection; warning is printed only once).
        - Threshold comes from the autolock config section. Gear codes
          are read from config too and fall back to the VSS defaults
          (126 = PARK, 0 = NEUTRAL) if not configured.
    '''

    # Input signal paths
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"

    # Output signal paths
    DRIVER_LOCK = "Vehicle.Cabin.Door.Row1.DriverSide.IsLocked"
    PASSENGER_LOCK = "Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked"

    # Fallback gear codes (VSS defaults)
    DEFAULT_GEAR_PARK = 126
    DEFAULT_GEAR_NEUTRAL = 0

    def __init__(self, kuksa: KuksaConnection, config, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state

        self.threshold = config["threshold_kmh"]
        self.gear_park = config.get("gear_park", self.DEFAULT_GEAR_PARK)
        self.gear_neutral = config.get("gear_neutral", self.DEFAULT_GEAR_NEUTRAL)

        # internal state to avoid repeated lock commands and log spam
        self.auto_locked = False
        self.door_warning_active = False

    def set_all_doors_locked(self, locked):
        '''Lock or unlock all available doors (True = locked). Extendable
        with additional door signals (e.g. Row2) in one place.'''
        self.kuksa.write(self.DRIVER_LOCK, locked)
        self.kuksa.write(self.PASSENGER_LOCK, locked)

    def run(self):
        if not self.vehicle_state.get("is_ready", False):
            return

        # Read current motion and door state from the broker
        try:
            speed = float(self.kuksa.get(self.SPEED_SIGNAL, 0))
            driver_locked = bool(self.kuksa.get(self.DRIVER_LOCK, False))
            passenger_locked = bool(self.kuksa.get(self.PASSENGER_LOCK, False))
            gear = int(self.kuksa.get(self.GEAR_SIGNAL, self.gear_park))
        except Exception as e:
            print(f"[AutoLock] Error: reading from broker failed: {e}")
            return

        moving = speed > self.threshold and gear not in (
            self.gear_park,
            self.gear_neutral,
        )

        if moving:
            # initial automatic lock when passing the speed threshold
            if not self.auto_locked:
                self.set_all_doors_locked(True)
                self.auto_locked = True
                print(f"[AutoLock] Info: threshold exceeded at "
                      f"{speed:.1f} km/h -> all doors locked")

            # permanent protection: override any unlock while moving
            elif not driver_locked or not passenger_locked:
                self.set_all_doors_locked(True)
                if not self.door_warning_active:
                    print(f"[AutoLock] Warning: door unlock attempt "
                          f"blocked at {speed:.1f} km/h")
                    self.door_warning_active = True
        else:
            # reset trigger flag once below threshold / not in drive
            if self.auto_locked:
                print("[AutoLock] Info: vehicle stopped or below "
                      "threshold -> autolock disarmed")
                self.auto_locked = False
            self.door_warning_active = False