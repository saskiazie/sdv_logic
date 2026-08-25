# DBC mapping required per signal

Reference for connecting this logic layer to the physical demonstrator.
Companion to `config/writemode_config.yaml`: that file decides **how** a signal
is written, this file lists **what has to exist on the bus** for the write to
have an effect.

This repository contains no mapping of its own. `Own_GUI_vss.json` is a pure
signal tree - it tells the databroker which signals exist, not which CAN
message carries them. The mapping lives in the DBC feeder configuration of the
demonstrator (`vss_dbc_front.json`, `vss_dbc_rear.json`), which is not part of
this project.

**Two directions, two consequences**

| Block | Direction | Needed for | Code change |
|-------|-----------|-----------|-------------|
| `dbc2vss` | CAN -> databroker | every signal a module **reads** | none - `get()` still reads the current value, only its source changes |
| `vss2dbc` | databroker -> CAN | every signal a module **writes** to a control unit | write mode `actuate` in `writemode_config.yaml` |

A signal without a mapping entry is known to the databroker by name but
connected to nothing. A write is accepted and stays without effect, and no
error is raised - which is why an unmapped signal is hard to notice.

---

## 1. Read signals - need `dbc2vss`

No code change. The modules keep calling `get()`; only the source of the value
changes from the CLI to a control unit.

| Signal | Zone | Read by | Counterpart on the bus |
|--------|------|---------|------------------------|
| `Vehicle.Cabin.Door.Row1.DriverSide.IsOpen` | front | StartSequence, AutoLock | exists (door control) |
| `Vehicle.Cabin.Door.Row1.PassengerSide.IsOpen` | front | AutoLock | exists (door control) |
| `Vehicle.ADAS.PDC.Rear.Distance` | rear | PDCLogic, UnrealSender | exists (parking sensors) |
| `Vehicle.Speed` | - | AutoLock, PowertrainSafety, UnrealSender | **none** - the demonstrator has no powertrain |
| `Vehicle.Powertrain.Transmission.CurrentGear` | - | AutoLock, PowertrainSafety, PDCLogic | **none** |
| `Vehicle.Powertrain.CombustionEngine.IsRunning` | - | StartSequence, PDCLogic | **none** |
| `Vehicle.Body.IgnitionState` | - | StartSequence | **none** |
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | - | StartSequence | **none** |
| `Vehicle.Body.Lights.*.IsEnabled` (3x) | - | IndicatorLogic | **none** - no physical stalk exists |

The signals marked **none** have no CAN counterpart on the demonstrator. They
were introduced by this work to model states the demonstrator does not
produce. They keep being fed from the CLI, from the demo script or from the
visualization, exactly as during verification - the mixed operation is
intentional and not a defect.

---

## 2. Written signals - need `vss2dbc`

These are the signals set to `actuate` in `writemode_config.yaml`. Each one
needs an entry in the mapping file of the zone whose bus carries it.

| Signal | Zone | Written by |
|--------|------|-----------|
| `Vehicle.Body.Lights.Beam.Low.IsOn` | front | LightsLogic |
| `Vehicle.Body.Lights.Running.IsOn` | front | LightsLogic |
| `Vehicle.Body.Lights.LightSwitch` | front | LightsLogic |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | front | LightsLogic |
| `Vehicle.Cabin.Door.Row1.DriverSide.IsLocked` | front | AutoLock |
| `Vehicle.Cabin.Door.Row1.PassengerSide.IsLocked` | front | AutoLock |
| `Vehicle.Body.Lights.Backup.IsOn` | rear | PDCLogic |
| `Vehicle.Body.Lights.Hazard.IsSignaling` | **front and rear** | IndicatorLogic, LightsLogic |
| `...DirectionIndicator.Left.IsSignaling` | **front and rear** | IndicatorLogic, LightsLogic |
| `...DirectionIndicator.Right.IsSignaling` | **front and rear** | IndicatorLogic, LightsLogic |

**The three indicator lamps are the special case.** A vehicle blinks front and
rear at the same time, so each of them needs an entry in *both* mapping files.
One VSS signal then drives two CAN messages on two buses. This is also the
point where the atomicity of `write_many()` stops helping: it guarantees that
all three values leave the databroker together, not that both zone controllers
switch in the same instant. If front and rear visibly drift apart, the cause is
the two bus paths, not the logic - and the fix belongs in the mapping (equal
`interval_ms`), not in `IndicatorLogic`.

---

## 3. Written signals without a receiver

| Signal | Written by | Why no mapping |
|--------|-----------|----------------|
| `Vehicle.ADAS.PDC.Rear.IsActive` | PDCLogic | derived state of this logic, no control unit executes it |
| `...HMI.DistanceWarningChime` | PDCLogic, LightsLogic | no sound-producing component exists on the demonstrator |
| `Vehicle.Body.Lights.*.IsEnabled` | IndicatorLogic | switch position, not an actuator |
| `Vehicle.Powertrain.Transmission.CurrentGear` | PowertrainSafety | restores a previously valid actual value |
| `Vehicle.Speed` | UnrealReceiver | measurement from the visualization |

These stay on `publish` in every setup. Adding a `vss2dbc` entry for them would
not fail - it would silently send a message no one listens to.

---

## 4. Entry format

The exact syntax belongs to the DBC feeder configuration of the demonstrator
and is documented there. The shape of one entry is:

```json
"vss2dbc": { "signal": "<DBC signal name>", "interval_ms": 100 },
"dbc2vss": { "signal": "<DBC signal name>", "interval_ms": 100 }
```

Prerequisite for either block: the DBC signal itself has to exist in the DBC
file of that zone. Where it does not - the parking distance values and
everything marked **none** in section 1 - the CAN message has to be defined
first. That is a change to the bus communication, not a configuration step.

After editing a mapping file the DBC feeder has to be restarted.

---

## 5. Checking

At the databroker, per signal: request the current value and the target value
separately. As long as they differ, the control unit has not executed the
request. If the current value never follows, either the mapping is incomplete
or the control unit does not answer.

One level deeper: `candump` on the virtual interface of the zone shows whether
the message leaves the databroker at all. That separates "the mapping is
missing" from "the control unit ignores it" - the two failures look identical
from the databroker.
