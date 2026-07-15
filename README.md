# SDV Logic with KUKSA Databroker

This project implements a modular **Software-Defined Vehicle (SDV)** logic in Python.
All vehicle logic runs as decentralized modules in a Linux VM and communicates
exclusively with the **Eclipse KUKSA Databroker** via gRPC.

An **Unreal Engine** project is used as the visualization front end (HMI). It receives
finished vehicle states over TCP and contains no logic of its own.

---

## System Requirements

- Linux (Ubuntu 20.04 / VirtualBox VM recommended)
- Python 3.8+
- Docker
- Unreal Engine 5 with a TCP socket plugin (optional - the logic runs without it)

---

## Architecture

```
+---------------------------- Ubuntu VM ----------------------------+
|                                                                   |
|   KUKSA Databroker (Docker container "Server", port 55555)        |
|            ^                                                      |
|            | gRPC (get_many / publish_many)                       |
|            v                                                      |
|   KuksaConnection   (thread-safe wrapper, one shared instance)    |
|            ^                                                      |
|   +--------+--------+---------+---------+---------+---------+     |
|   |        |        |         |         |         |         |     |
| Start-   Auto-   Powertrain  PDC-    Lights-  Indicator- Unreal-  |
| Sequence  Lock    Safety     Logic    Logic     Logic    Sender   |
|   |        |        |         |         |         |         |     |
|   +--------+--------+----+----+---------+---------+         |     |
|                          |                                  |     |
|              vehicle_state (shared dict)                    |     |
|      is_locked / is_unlocked / driver_access /              |     |
|      is_ready / hazard_enabled                              |     |
+-------------------------------------------------------------|-----+
                                                              |
                                       ASCII frame (10 fields, 50 Hz)
                                            TCP port 7010
                                                              v
                            +------------- Unreal Engine -------------+
                            |  BP_Transceiver2 (TCP client)           |
                            |    -> BP_VehicleAdvSportsCar (lights)   |
                            |    -> WBP_Dashboard (speed, hazard)     |
                            +-----------------------------------------+
```

| Part | Runs where | Role |
|------|-----------|------|
| KUKSA Databroker | Docker container `Server` | single source of truth for all signals |
| KuksaConnection | VM, shared by all threads | thread-safe gRPC access |
| Logic modules | VM, one daemon thread each | read signals, decide, publish signals |
| vehicle_state | VM, shared dict | coordination between the modules |
| UnrealSender | VM, TCP server | streams the visualization state |
| Unreal Engine | host or VM | renders finished states, no logic |

---

## Project Structure

Files not shown in the diagram above are helpers, configuration and
documentation - the logic itself is the seven modules plus the connection
wrapper.

sdv_logic/
- Logic_main.py - entry point, threading, module wiring
- kuksa_connection.py - thread-safe databroker wrapper
- config_loader.py - merges config/*config*.yaml
- init_kuksa_signals.py - baseline reset of all signals
- add_switch_signals.py - reference example: extend the VSS mapping
- start_sequence.py - access and startup state machine
- auto_lock.py - speed-dependent door locking
- powertrain_safety_logic.py - gear validation while moving
- pdc_logic.py - park distance control + backup light
- lights_logic.py - access lighting, DRL, feedback blink
- indicator_logic.py - turn indicators and hazard lights
- unreal_sender.py - TCP bridge to the Unreal HMI
- demo_drive.py - demo drive script (presentation only)
- dummy_sender.py - sends test frames without KUKSA
- Own_GUI_vss.json - VSS mapping used by the databroker
- requirements.txt

sdv_logic/config/
- base_config.yaml - kuksa host/port, system cycle time
- autolock_config.yaml - speed threshold, gear codes
- powertrain_config.yaml - gear codes, thresholds
- pdc_config.yaml - reverse gear threshold

sdv_logic/docs/
- used_vss_signals.md - signal reference per module
- architecture_overview.puml - system architecture
- vehicle_state_machine.puml - startup state machine
- sequence_startup.puml - startup sequence across modules
- activity_indicator_logic.puml - one indicator cycle

sdv_logic/test_files/
- test_config.py
- test_lights_logic.py
- test_unreal_client.py - TCP client to inspect the frame stream

---

## Full Setup (Copy & Paste One Command at a Time)

### System update
```bash
sudo apt update && sudo apt upgrade -y
```

### Install Docker
```bash
curl -fsSL https://get.docker.com | sudo sh
```
```bash
sudo usermod -aG docker $USER
```
```bash
sudo reboot
```

---

### Install Python and diagram tools
```bash
sudo apt install -y python3 python3-venv python3-pip
```
```bash
sudo apt install -y graphviz
```
`graphviz` is only needed to generate the UML diagrams (see Documentation).

---

### Clone repository
```bash
git clone <repository-url> && cd sdv_logic
```

---

### Create Python virtual environment and install dependencies
```bash
python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
```

---

## KUKSA Databroker Setup

### Create Docker network
```bash
docker network create kuksa
```

### Start KUKSA Databroker
```bash
docker run -d --name Server --network kuksa -p 55555:55555 -v $(pwd)/Own_GUI_vss.json:/data/vss.json ghcr.io/eclipse-kuksa/kuksa-databroker:main --insecure --vss /data/vss.json
```

The container only has to be created once. Afterwards:
```bash
docker start Server
```

`Own_GUI_vss.json` already contains every project-specific signal, so no
additional mapping step is required (see VSS Mapping below).

---

## Start the Logic Application
```bash
source venv/bin/activate && python3 Logic_main.py
```

If successful, the terminal prints:
```
[KuksaConnection] Info: successfully connected
[UnrealSender] Info: waiting for Unreal connection on port 7010
[Main] Info: SDV logic started
```

---

## Start KUKSA CLI (Second Terminal)
```bash
docker run -it --rm --network kuksa ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main --server Server:55555
```

If the databroker is hosted on a different network (e.g. 192.168.1.1):
```bash
docker run -it --rm --network kuksa ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main --server 192.168.1.1:55555
```

### Example CLI commands

Start the vehicle (in this order - the startup chain is strict):
```bash
publish Vehicle.Body.Access.KeyFob.IsUnlocked true
```
```bash
publish Vehicle.Cabin.Door.Row1.DriverSide.IsLocked false
```
```bash
publish Vehicle.Body.IgnitionState 3
```

Drive and trigger the safety logic:
```bash
publish Vehicle.Powertrain.Transmission.CurrentGear 127
```
```bash
publish Vehicle.Speed 30
```
```bash
publish Vehicle.Powertrain.Transmission.CurrentGear 126
```
```bash
get Vehicle.Powertrain.Transmission.CurrentGear
```

Indicators:
```bash
publish Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled true
```
```bash
publish Vehicle.Body.Lights.Hazard.IsEnabled true
```
```bash
subscribe Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling
```

A full signal reference per module is in `docs/used_vss_signals.md`.

---

## How It Works

- `Logic_main.py` starts **one daemon thread per logic module**
- Each module cyclically reads its input signals, decides, and publishes its output signals
- Two cycle rates are used:
  - **0.02 s (fast lane)**: LightsLogic, IndicatorLogic, UnrealSender - smooth blinking and frame rate
  - **0.1 s (standard)**: StartSequence, AutoLock, PowertrainSafetyLogic, PDCLogic
- All modules share **one** `KuksaConnection`. The underlying VSSClient is not
  thread-safe, so every gRPC call is serialized with a lock
- The modules **never call each other**. They exchange information only through the
  databroker and the shared `vehicle_state` dictionary
  (`is_locked`, `is_unlocked`, `driver_access`, `is_ready`, `hazard_enabled`)
- `StartSequence` unlocks the system: until `is_ready` is set, AutoLock, PDCLogic
  and PowertrainSafetyLogic return immediately
- `UnrealSender` acts as a TCP server on port 7010 and streams the visualization
  state to Unreal at 50 Hz
- All signals follow `Own_GUI_vss.json`

**Core design rule:** all decisions happen in the VM. Unreal receives finished states
(e.g. "the indicator lamp is on right now") and only renders them. Even the blink
rhythm is generated in Python, not in a Blueprint timer.

---

## VSS Mapping

The mapping is based on **VSS 4.1** and extended with project-specific signals.
`Own_GUI_vss.json` in this repository already contains all of them.

| Signal | Why it was added |
|--------|------------------|
| `Vehicle.Body.Access.KeyFob.IsUnlocked` | key fob unlock/lock request - no equivalent in VSS 4.1 |
| `Vehicle.Body.IgnitionState` | ignition switch position (0=LOCK, 1=OFF, 2=ACC, 3=ON) |
| `Vehicle.ADAS.PDC.Rear.IsActive` / `.Distance` | park distance control - VSS only models generic obstacle detection |
| `Vehicle.ADAS.PD.Front.IsActive` / `.Distance` | front person detection - prepared, not used by any module |
| `Vehicle.Cabin.Light.AmbientLight.IsLightOn` | one interior light for the whole cabin; VSS only models per-row lights |
| `Vehicle.Cabin.Infotainment.HMI.DistanceWarningChime` | acoustic warning tone (0=silent, 1=slow, 2=rapid, 3=solid) |
| `Vehicle.Body.Lights.Hazard.IsEnabled` | switch state, separate from the lamp state |
| `Vehicle.Body.Lights.DirectionIndicator.Left.IsEnabled` | same |
| `Vehicle.Body.Lights.DirectionIndicator.Right.IsEnabled` | same |

The three `*.IsEnabled` signals were inserted with `add_switch_signals.py`. That
script is kept as a **reference example** for extending the mapping
programmatically - it is not a setup step, since its result is already committed.
Running it again detects the existing signals and skips them.

After editing the mapping, the broker has to be restarted:
```bash
docker restart Server
```

---

## Configuration

All thresholds live in `config/*config*.yaml`. `config_loader.py` merges every file
matching that pattern into one dictionary, so the configuration can be split by
domain. Adding a new file requires no code change.

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

**Gear semantics** (project-specific interpretation of the int8 signal):
`< 0` = reverse, `0` = neutral, `126` = park, `127` = drive.

---

## Unreal Interface

`UnrealSender` acts as a TCP server on port 7010. Unreal connects as a client and
receives ASCII frames at 50 Hz:

```
speed;gear;hazard;backup;drl;lowbeam;interior;pdc;turnl;turnr|
30.00;127;0;0;1;0;0;999.0;1;0|
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

**Adding a field is a three-part change:** extend the frame in `unreal_sender.py`,
raise the `Length == 10` guard in `BP_Transceiver2` to the new count, and add the
corresponding GET node. If the guard and the frame disagree, Unreal silently
discards *every* frame.

The frame stream can be inspected without Unreal using `test_files/test_unreal_client.py`.

---

## Design Decisions

**Driver intent vs. light state.** Indicators use two signal layers: `*.IsEnabled` is
the switch (driver intent, stays constant), `*.IsSignaling` is the lamp (toggled by
`IndicatorLogic`). This mirrors real vehicle signal models and keeps Unreal free of
any timing logic.

**Blink frequency 1.5 Hz.** `BLINK_PERIOD = 0.333 s` per phase, full period 0.667 s.
This equals 90 flashes/min, the center of the ECE-R48 legal range of 60-120
flashes per minute.

**Hazard release clears the indicators (step 1a).** Switching the hazard warning off
also releases any engaged individual indicator. A real vehicle uses a mechanically
latched stalk and would keep the indicator running; the predictable
"hazard off = everything off" behavior was chosen deliberately.

**Left/right interlock on switch level (step 1b).** If both indicator switches are on
without hazard, the freshly pressed one wins and the opposite switch is actively
published as `false`. The conflict is resolved at the intent layer, so every reader
of the switches sees a consistent state - not just the lights.

**Logic never writes sensor values.** `PowertrainSafetyLogic` corrects the gear but
never writes `Vehicle.Speed`. A logic module overwriting a sensor would create two
competing sources of truth and fight the actual source every cycle. Invalid
acceleration is therefore reported, not "corrected".

**Thread safety.** The `VSSClient` is not thread-safe, but seven threads share one
connection. `KuksaConnection` serializes every gRPC call with a lock. Without it,
concurrent calls silently blocked each other for hundreds of milliseconds, which was
measurable as skipped indicator toggles.

**Atomic multi-signal writes.** `publish_many()` sends several values in one call, so
signals that must stay in sync (left/right indicator) can never drift apart. Active
channels republish their target state every cycle, which makes the system
self-healing: a lost publish is corrected within 20 ms.

**`vehicle_state` without a lock.** All writers set simple boolean flags, which is
atomic under the CPython GIL. A lock would add complexity without a measurable
benefit at these cycle rates.

**Frame fragments are discarded, not buffered.** TCP is a byte stream, so a read can
end mid-frame. Instead of a reassembly buffer, `BP_Transceiver2` validates the field
count and drops incomplete frames. At 50 Hz the next complete frame arrives 20 ms
later - the effort of a buffer is not justified for pure visualization.

---

## Known Limitations

- `IndicatorLogic` has no `is_ready` guard: indicators and hazard lights also work
  while the vehicle is locked and switched off. Intended for the hazard warning
  (as in a real vehicle), accepted for the individual indicators.
- While the unlock/lock feedback blink is running and an individual indicator is
  engaged at the same time, both `LightsLogic` and `IndicatorLogic` write the same
  `IsSignaling` signal. `IndicatorLogic` republishes every cycle and wins; the
  feedback flash may be suppressed in that rare case.
- `PowertrainSafetyLogic` only validates gears while the vehicle is moving.
  Undefined gear codes are tolerated at standstill.
- The brake light (`Vehicle.Body.Lights.Brake.IsActive`, mapped) is not implemented:
  no brake pedal signal is fed by any source in this setup.
- `Vehicle.ADAS.PD.Front.*` is mapped but not used by any module.

---

## Documentation

| Diagram | Question it answers |
|---------|--------------------|
| `docs/architecture_overview.puml` | Which part runs where, how does data flow? |
| `docs/vehicle_state_machine.puml` | How does the vehicle start up? |
| `docs/sequence_startup.puml` | Which module reacts when, in which order? |
| `docs/activity_indicator_logic.puml` | What happens inside one indicator cycle? |
| `classes_SDV_Logic.svg` | Which classes exist, what do they hold? |
| `packages_SDV_Logic.svg` | Which module imports which? |

The `.puml` sources render in VS Code with the PlantUML extension (Alt+D, render
mode `PlantUMLServer`).

The class and package diagrams are generated directly from the code:
```bash
pip install pylint
```
```bash
pyreverse -o svg -p SDV_Logic --colorized Logic_main.py kuksa_connection.py config_loader.py start_sequence.py auto_lock.py powertrain_safety_logic.py pdc_logic.py lights_logic.py indicator_logic.py unreal_sender.py
```

---

## Stop and Cleanup

### Stop the logic
```
Ctrl+C in the terminal running Logic_main.py
```

### Stop Databroker
```bash
docker stop Server && docker rm Server
```

### Remove Docker network (optional)
```bash
docker network rm kuksa
```

---

## Notes

- The logic runs headless - Unreal is optional and only visualizes
- `Vehicle.Speed` is fed externally (CLI or demo script); no module writes it
- Intended for simulation and development use
- Not intended for production vehicle systems