# SDV Logic with KUKSA Databroker

A modular Software-Defined Vehicle (SDV) demonstrator. All vehicle logic runs
as Python modules in a Linux VM and communicates exclusively through the
Eclipse KUKSA Databroker. Unreal Engine is used purely as a visualization
front end (HMI) and contains no logic of its own.

---

## Architecture

```
+---------------------------- Ubuntu VM ----------------------------+
|                                                                   |
|   KUKSA Databroker (Docker, port 55555)                           |
|            ^                                                      |
|            | gRPC (get_many / publish_many)                       |
|            v                                                      |
|   KuksaConnection  (thread-safe wrapper, one shared instance)     |
|            ^                                                      |
|   +--------+---------------------------------------------+       |
|   |        |            |            |          |        |       |
| StartSeq  AutoLock  PowertrainS.  PDCLogic  LightsLogic  ...      |
|   |        |            |            |          |        |       |
|   +--------------- vehicle_state (shared dict) ----------+        |
|                                                                   |
|   UnrealSender (TCP server, port 7010) --------------------+      |
+-----------------------------------------------------------|-------+
                                                            |
                                        ASCII frame (10 fields)
                                                            v
                            +-------------- Unreal Engine ------------+
                            |  BP_Transceiver2 (TCP client)           |
                            |    -> BP_VehicleAdvSportsCar (lights)   |
                            |    -> WBP_Dashboard (speed, hazard)     |
                            +-----------------------------------------+
```

**Core design rule:** all decisions happen in the VM. Unreal receives finished
states (e.g. "indicator light is on right now") and only renders them. Even the
blink rhythm is generated in Python, not in a Blueprint timer.

**Module decoupling:** the logic modules never call each other. They exchange
information only through the databroker and the shared `vehicle_state`
dictionary. This is why the generated class diagram shows no arrows between
them - none exist. The runtime coordination is visible in the sequence diagram
instead (`docs/sequence_startup.puml`).

**Threading:** `Logic_main.py` runs each module in its own daemon thread.
Two cycle rates are used:

| Lane | Cycle | Modules | Reason |
|------|-------|---------|--------|
| Fast | 0.02 s | LightsLogic, IndicatorLogic, UnrealSender | smooth blinking and frame rate |
| Standard | 0.1 s | StartSequence, AutoLock, PowertrainSafetyLogic, PDCLogic | state logic, no visual timing |

---

## System requirements

- Python 3.8+
- Eclipse KUKSA Databroker (run via Docker)
- Linux (Ubuntu recommended)
- Unreal Engine 5 with a TCP socket plugin (optional - the logic runs without it)

---

## Setup

```bash
# 1. virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt          # kuksa-client, pyyaml

# 2. start the databroker with the project's VSS mapping
docker run -it --rm --network kuksa -p 55555:55555 \
  -v $(pwd)/Own_GUI_vss.json:/vss.json \
  ghcr.io/eclipse-kuksa/kuksa-databroker:main --vss /vss.json

# 3. one-time: add the indicator switch signals to the mapping
python add_switch_signals.py             # then restart the databroker

# 4. run the logic
python Logic_main.py
```

The three `*.IsEnabled` switch signals are not part of the standard VSS
catalog. `add_switch_signals.py` inserts them into `Own_GUI_vss.json`. The
script is safe to re-run: existing signals are skipped.

---

## Project structure

```
sdv_logic/
├── Logic_main.py               # entry point, threading, module wiring
├── kuksa_connection.py         # thread-safe databroker wrapper
├── config_loader.py            # merges config/*config*.yaml
├── init_kuksa_signals.py       # baseline reset of all signals
├── add_switch_signals.py       # one-time VSS mapping extension
│
├── start_sequence.py           # access and startup state machine
├── auto_lock.py                # speed-dependent door locking
├── powertrain_safety_logic.py  # gear validation while moving
├── pdc_logic.py                # park distance control + backup light
├── lights_logic.py             # access lighting, DRL, feedback blink
├── indicator_logic.py          # turn indicators and hazard lights
├── unreal_sender.py            # TCP bridge to the Unreal HMI
│
├── config/
│   ├── base_config.yaml        # kuksa host/port, system cycle time
│   ├── autolock_config.yaml    # speed threshold, gear codes
│   ├── powertrain_config.yaml  # gear codes, thresholds
│   └── pdc_config.yaml         # reverse gear threshold
│
├── docs/
│   ├── used_vss_signals.md     # signal reference per module
│   ├── vehicle_state_machine.puml
│   ├── architecture_overview.puml
│   ├── sequence_startup.puml
│   └── activity_indicator_logic.puml
│
└── Own_GUI_vss.json            # VSS mapping used by the databroker
```

---

## Configuration

All thresholds live in `config/*config*.yaml`. `config_loader.py` merges every
file matching that pattern into one dictionary, so the configuration can be
split by domain. Adding a new file requires no code change.

```yaml
# base_config.yaml
system:
  cycle_time_s: 0.1
kuksa:
  host: "127.0.0.1"
  port: 55555

# autolock_config.yaml
autolock:
  threshold_kmh: 20
  gear_park: 126        # optional, falls back to the VSS default
  gear_neutral: 0       # optional

# powertrain_config.yaml
powertrain:
  gear_neutral: 0
  gear_park: 126
  gear_drive: 127
  reverse_gear_threshold: 0
  moving_speed_threshold_kmh: 0

# pdc_config.yaml
pdc:
  reverse_gear_threshold: 0
```

**Gear semantics** (project-specific mapping): `< 0` = reverse, `0` = neutral,
`126` = park, `127` = drive.

---

## Unreal interface

`UnrealSender` acts as a TCP server on port 7010. Unreal connects as a client
and receives ASCII frames at 50 Hz:

```
speed;gear;hazard;backup;drl;lowbeam;interior;pdc;turnl;turnr|
0.00;127;1;0;1;0;0;999.0;1;0|
```

| Index | Signal | Type |
|-------|--------|------|
| 0 | Vehicle.Speed | float (2 decimals) |
| 1 | Vehicle.Powertrain.Transmission.CurrentGear | int |
| 2 | Vehicle.Body.Lights.Hazard.IsSignaling | 0/1 |
| 3 | Vehicle.Body.Lights.Backup.IsOn | 0/1 |
| 4 | Vehicle.Body.Lights.Running.IsOn | 0/1 |
| 5 | Vehicle.Body.Lights.Beam.Low.IsOn | 0/1 |
| 6 | Vehicle.Cabin.Light.AmbientLight.IsLightOn | 0/1 |
| 7 | Vehicle.ADAS.PDC.Rear.Distance | float (1 decimal) |
| 8 | Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling | 0/1 |
| 9 | Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling | 0/1 |

**Adding a field is a three-part change:** extend the frame in
`unreal_sender.py`, raise the `Length == 10` guard in `BP_Transceiver2` to the
new count, and add the corresponding GET node. If the guard and the frame
disagree, Unreal silently discards *every* frame.

---

## Design decisions

**Driver intent vs. light state.** Indicators use two signal layers:
`*.IsEnabled` is the switch (driver intent, stays constant), `*.IsSignaling` is
the lamp (toggled by `IndicatorLogic`). This mirrors real vehicle signal models
and keeps Unreal free of any timing logic.

**Blink frequency 1.5 Hz.** `BLINK_PERIOD = 0.333 s` per phase, full period
0.667 s. This equals 90 flashes/min, the center of the ECE-R48 legal range of
60-120 flashes per minute.

**Hazard release clears the indicators (step 1a).** Switching the hazard
warning off also releases any engaged individual indicator. A real vehicle uses
a mechanically latched stalk and would keep the indicator running; the
predictable "hazard off = everything off" behavior was chosen deliberately.

**Left/right interlock on switch level (step 1b).** If both indicator switches
are on without hazard, the freshly pressed one wins and the opposite switch is
actively published as `false`. The conflict is resolved at the intent layer, so
every reader of the switches sees a consistent state - not just the lights.

**Logic never writes sensor values.** `PowertrainSafetyLogic` corrects the gear
but never writes `Vehicle.Speed`. A logic module overwriting a sensor would
create two competing sources of truth and fight the actual source every cycle.
Invalid acceleration is therefore reported, not "corrected".

**Thread safety.** The `VSSClient` is not thread-safe, but seven threads share
one connection. `KuksaConnection` serializes every gRPC call with a lock.
Without it, concurrent calls silently blocked each other for hundreds of
milliseconds, which was measurable as skipped indicator toggles.

**Atomic multi-signal writes.** `publish_many()` sends several values in one
call, so signals that must stay in sync (left/right indicator) can never drift
apart. Active channels republish their target state every cycle, which makes
the system self-healing: a lost publish is corrected within 20 ms.

**`vehicle_state` without a lock.** All writers set simple boolean flags, which
is atomic under the CPython GIL. A lock would add complexity without a
measurable benefit at these cycle rates.

**Frame fragments are discarded, not buffered.** TCP is a byte stream, so a
read can end mid-frame. Instead of a reassembly buffer, `BP_Transceiver2`
validates the field count and drops incomplete frames. At 50 Hz the next
complete frame arrives 20 ms later - the effort of a buffer is not justified
for pure visualization.

---

## Known limitations

- `IndicatorLogic` has no `is_ready` guard: indicators and hazard lights also
  work while the vehicle is locked and switched off. Intended for the hazard
  warning (as in a real vehicle), accepted for the individual indicators.
- While the unlock/lock feedback blink is running and an individual indicator
  is engaged at the same time, both `LightsLogic` and `IndicatorLogic` write
  the same `IsSignaling` signal. `IndicatorLogic` republishes every cycle and
  wins; the feedback flash may be suppressed in that rare case.
- `PowertrainSafetyLogic` only validates gears while the vehicle is moving.
  Undefined gear codes are tolerated at standstill.
- Brake light (`Vehicle.Body.Lights.Brake.IsActive`) is not implemented: no
  brake pedal signal exists in this setup (see outlook).

---

## Outlook

**Pedal feedback channel from Unreal.** The TCP connection is full duplex, so
Unreal could send driver inputs back to the VM (`IN;throttle;brake|`). The
target signals `Vehicle.Chassis.Accelerator.PedalPosition` and
`Vehicle.Chassis.Brake.PedalPosition` already exist in the VSS mapping but are
fed by no source. With them, the brake light could be derived from the actual
pedal instead of estimated from deceleration, and Unreal would become the plant
model while the VM stays the control unit. This does not break the
architecture rule: pedal positions are sensor data, not logic.

**Vehicle model exchange.** `BP_Transceiver2` currently casts to
`BP_VehicleAdvSportsCar`. A Blueprint interface (`BPI_VSSVehicle`) would make
the vehicle model exchangeable without touching the transceiver.

---

## Documentation

| Diagram | Question it answers |
|---------|--------------------|
| `architecture_overview.puml` | Which part runs where, how does data flow? |
| `vehicle_state_machine.puml` | How does the vehicle start up? |
| `sequence_startup.puml` | Which module reacts when, in which order? |
| `activity_indicator_logic.puml` | What happens inside one indicator cycle? |
| `classes_SDV_Logic.svg` | Which classes exist, what do they hold? |
| `packages_SDV_Logic.svg` | Which module imports which? |

The `.puml` sources render in VS Code with the PlantUML extension (Alt+D).
The class and package diagrams are generated from the code:

```bash
pyreverse -o svg -p SDV_Logic --colorized \
  Logic_main.py kuksa_connection.py config_loader.py start_sequence.py \
  auto_lock.py powertrain_safety_logic.py pdc_logic.py lights_logic.py \
  indicator_logic.py unreal_sender.py
```