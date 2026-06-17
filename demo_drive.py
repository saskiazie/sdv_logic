"""
demo_drive.py - feeds the vehicle input signals into KUKSA step by step.

Runs as a second process next to Logic_main.py: Logic_main reacts, this script
only sets the inputs. Uses publish() (current values) so the logic modules read
them back via get(). Step through the sequence with Enter.
"""
import time
from config_loader import load_configs
from kuksa_connection import KuksaConnection

# Signal paths - keep in sync with the logic modules
KEYFOB   = "Vehicle.Body.Access.KeyFob.IsUnlocked"
DRIVERLK = "Vehicle.Cabin.Door.Row1.DriverSide.IsLocked"
IGNITION = "Vehicle.Body.IgnitionState"
GEAR     = "Vehicle.Powertrain.Transmission.CurrentGear"
SPEED    = "Vehicle.Speed"
PDC_DIST = "Vehicle.ADAS.PDC.Rear.Distance"

# Gear codes / ignition states
PARK, NEUTRAL, DRIVE, REVERSE = 126, 0, 127, -1     # REVERSE must be below reverse_gear_threshold
IGN_LOCK, IGN_OFF, IGN_ACC, IGN_ON = 0, 1, 2, 3

# Speed for the auto-lock step - has to exceed autolock.threshold_kmh
DRIVE_SPEED = 30.0


def banner(text):
    print("\n" + "=" * 66)
    print(text)
    print("=" * 66)


def main():
    config = load_configs()
    kuksa = KuksaConnection(host=config["kuksa"]["host"], port=config["kuksa"]["port"])
    print("---- Demo driver connecting to KUKSA ----")
    if not kuksa.connect():
        print("[ERROR] No connection to KUKSA - is the databroker running?")
        return

    def publish(signal, value):
        try:
            kuksa.publish(signal, value)
            print(f"   set: {signal} = {value}")
        except Exception as e:
            print(f"   [WARN] could not set {signal}: {e}")

    def step(title, watch, sets):
        banner(title)
        print("In the logic terminal you should see:")
        print(f"   -> {watch}")
        input("\n   [Enter] to trigger ...")
        for sig, val in sets:
            publish(sig, val)
        time.sleep(0.5)   # let the logic thread react (~0.1s cycle)

    # Clean start: vehicle locked, ignition off
    banner("Baseline: bring the vehicle into the locked initial state")
    for sig, val in [(KEYFOB, False), (IGNITION, IGN_LOCK), (DRIVERLK, True),
                     (GEAR, PARK), (SPEED, 0.0), (PDC_DIST, 999.0)]:
        publish(sig, val)
    time.sleep(0.5)

    print("\nPrerequisite: 'python3 Logic_main.py' is already running in another")
    print("terminal. Then press [Enter] here to start the demo.")
    input()

    step("1) Key fob: UNLOCK",
         "Unlock detected, baseline reset, interior light on + double hazard blink",
         [(KEYFOB, True)])

    step("2) Driver gets in (driver door unlocked)",
         "Driver access granted -> waiting for ignition",
         [(DRIVERLK, False)])

    step("3) Ignition to ACC",
         "Ignition ACC detected",
         [(IGNITION, IGN_ACC)])

    step("4) Ignition to ON  ->  vehicle becomes READY",
         "Ignition ON accepted, state READY, Engine started, daytime running lights (DRL) on",
         [(IGNITION, IGN_ON)])

    step("5) Shift into D",
         "(no warning - valid gear)",
         [(GEAR, DRIVE)])

    step(f"6) Drive off ({DRIVE_SPEED:.0f} km/h)  ->  automatic door locking",
         "Auto-Lock: Target speed exceeded -> All doors locked",
         [(SPEED, DRIVE_SPEED)])

    step("7) SAFETY: shift into PARK while moving",
         "Safety warning: Shift to Park while moving not allowed (gear is reset)",
         [(GEAR, PARK)])

    step("8) Stop",
         "Autolock disarmed (vehicle below threshold)",
         [(SPEED, 0.0)])

    step("9) Reverse gear  ->  PDC + backup light",
         "PDC: Rear parking sensor activated (backup light on)",
         [(GEAR, REVERSE)])

    step("10) Obstacle at 120 cm  ->  slow beep",
         "Buzzer slow (level 1, 0.8s interval)",
         [(PDC_DIST, 120.0)])

    step("11) Closer: 80 cm  ->  fast beep",
         "Buzzer fast (level 2, 0.3s interval)",
         [(PDC_DIST, 80.0)])

    step("12) Very close: 30 cm  ->  solid tone",
         "Buzzer solid tone (level 3)",
         [(PDC_DIST, 30.0)])

    step("13) Park & LOCK",
         "Lock request, Engine stopped, all lights off, double blink + buzzer",
         [(GEAR, PARK), (SPEED, 0.0), (PDC_DIST, 999.0), (KEYFOB, False)])

    banner("Demo finished - vehicle is locked again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo aborted.")