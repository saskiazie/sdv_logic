# Used VSS signals

Reference of every signal used in this project, listed per module and per
signal. Derived from the module sources and `Own_GUI_vss.json` (VSS 4.1 base)
- keep in sync when signals are added.

**Access types**
- **read** - `kuksa.get()` / `kuksa.get_many()` (current value)
- **write** - `kuksa.publish()` / `kuksa.publish_many()` (current value)

No module writes target values. `KuksaConnection.set()` exists but is unused:
in this setup no control unit sits behind the broker, so the logic is itself
the provider of every signal it writes. See "System boundary" at the end of
this file.

---

## 1. Signals per module

### StartSequence (`start_sequence.py`, 0.1 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | read | unlock / lock request |
| `Vehicle.Cabin.Door.Row1.DriverSide.IsLocked` | read | driver access validation |
| `Vehicle.Body.IgnitionState` | read | 0=LOCK, 1=OFF, 2=ACC, 3=ON |
| `Vehicle.Powertrain.CombustionEngine.IsRunning` | read / write | engine start and stop |

Internal state written: `vehicle_state["is_locked" | "is_unlocked" | "driver_access" | "is_ready"]`

---

### AutoLock (`auto_lock.py`, 0.1 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Speed` | read | threshold comparison |
| `Vehicle.Powertrain.Transmission.CurrentGear` | read | only lock in a driving gear |
| `Vehicle.Cabin.Door.Row1.DriverSide.IsLocked` | read / write | lock, and override unlock attempts |
| `Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked` | read / write | same for the passenger door |

Guard: inactive until `vehicle_state["is_ready"]`.

---

### PowertrainSafetyLogic (`powertrain_safety_logic.py`, 0.1 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Speed` | read | motion detection (never written, see design decision) |
| `Vehicle.Powertrain.Transmission.CurrentGear` | read / write | restore the last valid gear |

Guard: inactive until `vehicle_state["is_ready"]`.

---

### PDCLogic (`pdc_logic.py`, 0.1 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Powertrain.Transmission.CurrentGear` | read | reverse detection |
| `Vehicle.Powertrain.CombustionEngine.IsRunning` | read | only active with the engine running |
| `Vehicle.ADAS.PDC.Rear.Distance` | read | obstacle distance in cm |
| `Vehicle.ADAS.PDC.Rear.IsActive` | write | sensor system state |
| `Vehicle.Body.Lights.Backup.IsOn` | write | reverse light |
| `Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime` | write | 0=silent, 1=slow, 2=rapid, 3=solid |

Guard: inactive until `vehicle_state["is_ready"]`. Chime writes go through
`safe_kuksa_publish()`, so an unmapped chime signal cannot break the module.

---

### LightsLogic (`lights_logic.py`, 0.02 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Body.Lights.LightSwitch` | write | "OFF" / "DAYTIME_RUNNING_LIGHTS" |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | write | welcome light, 5 s timeout |
| `Vehicle.Body.Lights.Running.IsOn` | write | daytime running lights |
| `Vehicle.Body.Lights.Beam.Low.IsOn` | write | reset on lock only |
| `Vehicle.Body.Lights.Hazard.IsSignaling` | write | unlock / lock feedback blink |
| `Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling` | write | feedback blink (see note) |
| `Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling` | write | feedback blink (see note) |
| `Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime` | write | short lock confirmation beep |

Reads no VSS signals - reacts only to `vehicle_state`.

**Note:** the feedback blink drives all three `IsSignaling` signals in one
`publish_many()` call. Unreal executes `SetTurnLeft` / `SetTurnRight` after
`SetHazard` within the same frame and would otherwise overwrite the blinker
materials with their idle state.

---

### IndicatorLogic (`indicator_logic.py`, 0.02 s)

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Body.Lights.Hazard.IsEnabled` | read | hazard switch (driver intent) |
| `Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled` | read / write | left switch; written by interlock and hazard release |
| `Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled` | read / write | right switch; same |
| `Vehicle.Body.Lights.Hazard.IsSignaling` | write | hazard lamp state |
| `Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling` | write | left lamp state |
| `Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling` | write | right lamp state |

Internal state written: `vehicle_state["hazard_enabled"]`

The three `*.IsEnabled` signals are **not part of the standard VSS catalog** -
they are added by `add_switch_signals.py` (boolean, actuator).

No `is_ready` guard: indicators work with the vehicle locked and off.

---

### UnrealSender (`unreal_sender.py`, 0.02 s)

Read-only. All twelve signals are fetched in one `get_many()` call; the order
is the frame field order.

| Index | Signal |
|-------|--------|
| 0 | `Vehicle.Speed` |
| 1 | `Vehicle.Powertrain.Transmission.CurrentGear` |
| 2 | `Vehicle.Body.Lights.Hazard.IsSignaling` |
| 3 | `Vehicle.Body.Lights.Backup.IsOn` |
| 4 | `Vehicle.Body.Lights.Running.IsOn` |
| 5 | `Vehicle.Body.Lights.Beam.Low.IsOn` |
| 6 | `Vehicle.Cabin.Light.AmbientLight.IsLightOn` |
| 7 | `Vehicle.ADAS.PDC.Rear.Distance` |
| 8 | `Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling` |
| 9 | `Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling` |
| 10 | `Vehicle.Chassis.Accelerator.PedalPosition` |
| 11 | `Vehicle.Chassis.SteeringWheel.Angle` |

Fields 10 and 11 are driver inputs travelling in a circle: Unreal reads the
pedal and the wheel, the values reach the broker, and the same values are sent
back so the visualization drives the vehicle from the signal rather than from
its own input. This keeps the databroker the single source of truth even for
values that originate in Unreal.

---

### UnrealReceiver (`unreal_receiver.py`, 0.02 s)

Write-only. Receives measured values from Unreal over TCP (port 7011) and
publishes them.

| Signal | Access | Purpose |
|--------|--------|---------|
| `Vehicle.Speed` | write | measured road speed from the Chaos physics engine |

The vehicle is moved by Unreal's physics, so the actual road speed only exists
there. Without this channel two truths would compete: the speed derived from
the pedal in the VM and the speed the vehicle really reaches. The module makes
the simulated vehicle a signal source like any other sensor - it reports a
measurement, it does not decide anything.

Values are published only when they changed by more than `SPEED_EPSILON`
(0.1 km/h), so a constant speed does not put 50 writes per second on the broker.

---

### init_kuksa_signals (`init_kuksa_signals.py`, once at startup)

Write-only baseline. Every write is individually guarded; unmapped signals are
collected and reported instead of raising.

| Signal | Baseline |
|--------|----------|
| `Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen` | `False` |
| `Vehicle.Cabin.Door.Row1.DriverSide.IsOpen` | `False` |
| `Vehicle.Powertrain.CombustionEngine.IsRunning` | `False` |
| `Vehicle.Body.Lights.Hazard.IsSignaling` | `False` |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | `False` |
| `Vehicle.Speed` | `0.0` |
| `Vehicle.Powertrain.Transmission.CurrentGear` | `126` (park) |
| `Vehicle.ADAS.PDC.Rear.IsActive` | `False` |
| `Vehicle.ADAS.PDC.Rear.Distance` | `999.0` |
| `Vehicle.Body.Lights.Backup.IsOn` | `False` |
| `Vehicle.LowVoltageSystemState` | `"LOCK"` |
| `Vehicle.Body.IgnitionState` | `0` (LOCK) |
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | `False` |

---

### KuksaConnection / config_loader

No signals. `KuksaConnection` is the transport layer (thread-safe wrapper
around `VSSClient`); `config_loader` reads YAML files only.

---

## 2. Writer matrix

Which module owns which signal. A signal with exactly one writer has a single
source of truth; the two exceptions are documented below.

| Signal | Written by | Read by |
|--------|-----------|---------|
| `Vehicle.Speed` | UnrealReceiver (measurement) | AutoLock, PowertrainSafety, UnrealSender |
| `Vehicle.Powertrain.Transmission.CurrentGear` | PowertrainSafety (corrections) | AutoLock, PowertrainSafety, PDCLogic, UnrealSender |
| `Vehicle.Powertrain.CombustionEngine.IsRunning` | StartSequence | StartSequence, PDCLogic |
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | *external / init* | StartSequence |
| `Vehicle.Body.IgnitionState` | *external / init* | StartSequence |
| `Vehicle.Cabin.Door.Row1.DriverSide.IsLocked` | AutoLock | AutoLock, StartSequence |
| `Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked` | AutoLock | AutoLock |
| `Vehicle.Body.Lights.LightSwitch` | LightsLogic | - |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | LightsLogic | UnrealSender |
| `Vehicle.Body.Lights.Running.IsOn` | LightsLogic | UnrealSender |
| `Vehicle.Body.Lights.Beam.Low.IsOn` | LightsLogic | UnrealSender |
| `Vehicle.Body.Lights.Hazard.IsEnabled` | *external (switch)* | IndicatorLogic |
| `...DirectionIndicator.Left.IsEnabled` | *external* + IndicatorLogic (interlock) | IndicatorLogic |
| `...DirectionIndicator.Right.IsEnabled` | *external* + IndicatorLogic (interlock) | IndicatorLogic |
| `Vehicle.Body.Lights.Hazard.IsSignaling` | IndicatorLogic **and** LightsLogic | UnrealSender |
| `...DirectionIndicator.Left.IsSignaling` | IndicatorLogic **and** LightsLogic | UnrealSender |
| `...DirectionIndicator.Right.IsSignaling` | IndicatorLogic **and** LightsLogic | UnrealSender |
| `Vehicle.ADAS.PDC.Rear.IsActive` | PDCLogic | - |
| `Vehicle.ADAS.PDC.Rear.Distance` | *external (sensor)* | PDCLogic, UnrealSender |
| `Vehicle.Body.Lights.Backup.IsOn` | PDCLogic | UnrealSender |
| `...HMI.DistanceWarningChime` | PDCLogic, LightsLogic | - |
| `Vehicle.Chassis.Accelerator.PedalPosition` | *external (Unreal input)* | UnrealSender |
| `Vehicle.Chassis.SteeringWheel.Angle` | *external (Unreal input)* | UnrealSender |

**Two writers on the `IsSignaling` signals - resolved by priority.**
`IndicatorLogic` owns them while a switch is engaged. `LightsLogic` only drives
them for the short unlock/lock feedback blink and steps back whenever
`vehicle_state["hazard_enabled"]` is true. The remaining overlap (feedback
blink while an individual indicator is engaged) is a known limitation, see
README.

---

## 3. Non-standard signals

| Signal | Reason | Added by |
|--------|--------|----------|
| `Vehicle.Body.Lights.Hazard.IsEnabled` | switch state, separate from the lamp state | `add_switch_signals.py` |
| `...DirectionIndicator.Left.IsEnabled` | same | `add_switch_signals.py` |
| `...DirectionIndicator.Right.IsEnabled` | same | `add_switch_signals.py` |
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | key fob request, no VSS equivalent | manually |
| `Vehicle.Body.IgnitionState` | ignition switch position (uint8) | manually |
| `Vehicle.ADAS.PDC.Rear.IsActive` / `.Distance` | park distance control | manually |
| `Vehicle.ADAS.PD.Front.IsActive` / `.Distance` | front person detection, unused | manually |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | one cabin light instead of per-row lights | manually |
| `Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime` | acoustic warning tone (uint8) | manually |

Standard VSS models indicators with `IsSignaling` only, which mixes driver
intent and lamp state in one signal. Splitting them keeps the blink logic in
the VM and lets the switches stay constant while the lamp toggles.

---

## 4. Mapped but unused

These signals have been added in `Own_GUI_vss.json` but no module reads or writes them.
Listed here so that anyone browsing the mapping does not search the code for a
logic that was never written.

### Brake light chain (one connected gap)

| Signal | Status |
|--------|--------|
| `Vehicle.Chassis.Brake.PedalPosition` | brake pedal 0-100 %, fed by no source |
| `Vehicle.Body.Lights.Brake.IsActive` | brake lamp, string enum INACTIVE / ACTIVE / ADAPTIVE |

These two form one chain. In a real vehicle the cause (pedal pressed) drives
the effect (brake lamp on). No source feeds the brake pedal position, so the
cause is missing and the brake light cannot be driven from it. Deriving braking
from the change of `Vehicle.Speed` would only estimate it indirectly and was
therefore not implemented.

The accelerator pedal shows what the missing piece would look like: it is fed
from Unreal and travels through the broker like any other input. A brake pedal
field in the same frame would close this chain the same way, without breaking
the architecture rule - pedal positions are measurements, not decisions.

### Other

| Signal | Status |
|--------|--------|
| `Vehicle.ADAS.PD.Front.IsActive` / `.Distance` | front person detection, prepared in the mapping but not implemented |

---

## 5. System boundary

Every signal above is written as a **current value**. That is correct for this
setup and only for this setup: the broker is fed by the CLI, by the demo script
and by Unreal, and no control unit sits behind it. Where a real vehicle would
have a provider that executes a request and reports back what actually
happened, the logic here has to do both jobs at once - it decides, and it
states the result as fact.

On the wired demonstrator the signals owned by a control unit would have to be
written as **target values** instead (`kuksa.set()` / `actuate` in the CLI),
and the control unit would report the current value back through the
`dbc2vss` mapping. Which signals are affected, and which two cases cannot be
converted by changing the method alone, is documented in the `hardware-writemode`
branch.