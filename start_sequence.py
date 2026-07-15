from kuksa_connection import KuksaConnection

class StartSequence:
    '''
    Vehicle access and startup sequence.

    Purpose:
        Detects key fob unlock/lock requests, validates driver access
        and the ignition state, starts and stops the engine, and sets
        the central vehicle_state flags for all other modules.

    Input signals:
        Vehicle.Body.Access.KeyFob.IsUnlocked
        Vehicle.Cabin.Door.Row1.DriverSide.IsLocked
        Vehicle.Body.IgnitionState   (0=LOCK, 1=OFF, 2=ACC, 3=ON)

    Output signals:
        Vehicle.Powertrain.CombustionEngine.IsRunning
        vehicle_state["is_locked" | "is_unlocked" |
                      "driver_access" | "is_ready"]

    Notes:
        - Lighting feedback is handled separately by LightsLogic;
          StartSequence only updates the vehicle state.
        - The startup chain is strict: unlock -> driver door opened ->
          ignition ON. Ignition without prior driver access is ignored
          (warning printed once).
        - Ignition LOCK/OFF always drops readiness and stops the
          engine (fallback, step 6).
    '''

    # Input signal paths
    KEYFOB_SIGNAL = "Vehicle.Body.Access.KeyFob.IsUnlocked"
    DRIVER_LOCK_SIGNAL = "Vehicle.Cabin.Door.Row1.DriverSide.IsLocked"
    IGNITION_STATE_SIGNAL = "Vehicle.Body.IgnitionState"

    # Ignition state values (uint8 actuator)
    IGNITION_LOCK = 0
    IGNITION_OFF = 1
    IGNITION_ACC = 2
    IGNITION_ON = 3

    # Output signal paths
    ENGINE_RUNNING_SIGNAL = "Vehicle.Powertrain.CombustionEngine.IsRunning"

    def __init__(self, kuksa: KuksaConnection, vehicle_state):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state  # shared state dictionary

        # one-shot flags for the sequence steps
        self.unlock_done = False
        self.lock_done = True   # vehicle starts in locked state
        self.driver_entry_done = False
        self.ignition_on_triggered = False
        self.ignition_acc_triggered = False
        self.ignition_missing_entry_warning_printed = False

    def run(self):
        # read the current access and ignition state from the broker
        try:
            keyfob_unlocked = bool(
                self.kuksa.get(self.KEYFOB_SIGNAL, False))
            driver_door_locked = bool(
                self.kuksa.get(self.DRIVER_LOCK_SIGNAL, True))
            ignition_state = int(
                self.kuksa.get(self.IGNITION_STATE_SIGNAL,
                               self.IGNITION_LOCK))
        except Exception as e:
            print(f"[StartSequence] Error: reading from broker "
                  f"failed: {e}")
            return

        # 1. Unlock request
        if keyfob_unlocked and not self.unlock_done:
            print("[StartSequence] Info: key fob unlock request detected")

            self.vehicle_state["is_locked"] = False
            self.vehicle_state["is_unlocked"] = True
            self.vehicle_state["driver_access"] = False
            self.vehicle_state["is_ready"] = False

            self.unlock_done = True
            self.lock_done = False
            self.driver_entry_done = False
            self.ignition_on_triggered = False
            self.ignition_missing_entry_warning_printed = False

            print("[StartSequence] Info: vehicle state set to UNLOCKED")

        # 2. Lock request
        if not keyfob_unlocked and not self.lock_done:
            print("[StartSequence] Info: key fob lock request detected")

            self.vehicle_state["is_locked"] = True
            self.vehicle_state["is_unlocked"] = False
            self.vehicle_state["driver_access"] = False
            self.vehicle_state["is_ready"] = False

            self.unlock_done = False
            self.lock_done = True
            self.driver_entry_done = False
            self.ignition_on_triggered = False
            self.ignition_missing_entry_warning_printed = False

            if bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False)):
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, False)
                print("[StartSequence] Info: engine stopped due to "
                      "lock request")

            print("[StartSequence] Info: vehicle state set to LOCKED")

        # 3. Driver access validation
        if (self.unlock_done and not driver_door_locked
                and not self.driver_entry_done):
            self.vehicle_state["driver_access"] = True
            self.driver_entry_done = True
            self.ignition_missing_entry_warning_printed = False

            print("[StartSequence] Info: driver door unlocked -> access "
                  "granted, waiting for ignition")

        # 4. Ignition validation
        if self.unlock_done and ignition_state == self.IGNITION_ACC:
            if not self.ignition_acc_triggered:
                print("[StartSequence] Info: ignition ACC detected")
                self.ignition_acc_triggered = True

        elif self.unlock_done and ignition_state == self.IGNITION_ON:
            if not self.driver_entry_done:
                if not self.ignition_missing_entry_warning_printed:
                    print("[StartSequence] Warning: ignition ignored - "
                          "driver access missing")
                    self.ignition_missing_entry_warning_printed = True
                return

            if not self.ignition_on_triggered:
                self.vehicle_state["is_ready"] = True
                self.ignition_on_triggered = True

                print("[StartSequence] Info: ignition ON accepted")
                print("[StartSequence] Info: vehicle state set to READY")

        # 5. Engine startup
        if (self.vehicle_state.get("is_ready", False)
                and ignition_state == self.IGNITION_ON):
            is_engine_running = bool(
                self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False))

            if not is_engine_running:
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, True)
                print("[StartSequence] Info: engine started")

        # 6. Ignition off / lock fallback
        if ignition_state in (self.IGNITION_LOCK, self.IGNITION_OFF):
            self.ignition_on_triggered = False
            self.ignition_acc_triggered = False
            self.vehicle_state["is_ready"] = False

            if bool(self.kuksa.get(self.ENGINE_RUNNING_SIGNAL, False)):
                self.kuksa.publish(self.ENGINE_RUNNING_SIGNAL, False)
                print("[StartSequence] Info: ignition OFF/LOCK - "
                      "engine stopped")