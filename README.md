# SDV Logic with KUKSA Databroker

This project implements a modular **Software-Defined Vehicle (SDV)** logic in Python.
All vehicle logic runs as decentralized modules in a Linux VM and communicates
exclusively with the **Eclipse KUKSA Databroker** via gRPC.

An **Unreal Engine** project is used as the visualization front end (HMI). It receives
finished vehicle states over TCP and contains no logic of its own.

---

## System Requirements

- Linux (Ubuntu 20.04 in a VirtualBox VM)
- Python 3.8+
- Docker
- Unreal Engine 5 with a TCP socket plugin (optional - the logic runs without it)

### Verified environment

The versions this project was developed and tested with. Newer ones are likely
to work, but only these were actually used - the gRPC API of `kuksa-client` in
particular has changed between releases.

| Component | Where it runs | Version |
|-----------|---------------|---------|
| Oracle VirtualBox | Windows host | 7.1.2 |
| Ubuntu | VM | 20.04 LTS |
| Python | VM | 3.8.10 |
| `kuksa-client` | VM (pip) | 0.5.1 |
| `pyyaml` | VM (pip) | see `requirements.txt` |
| Docker Engine | VM | 26.1.3 |
| KUKSA Databroker image | VM (container) | tag `main`, built 01/04/2026 |
| KUKSA Databroker CLI | VM (container) | v0.6.1-dev.0 |
| VSS catalog | `Own_GUI_vss.json` | 4.1 + project extensions |
| Unreal Engine | Windows host | 5.7.4 |
| TCP socket plugin | Unreal project | 1.8.0 |

The databroker image tag `main` moves. If you need the exact state:

```bash
docker image inspect ghcr.io/eclipse-kuksa/kuksa-databroker:main --format '{{.Created}}  {{index .RepoDigests 0}}'
```

**The logic runs in the VM, Unreal runs on the Windows host.** The two are
connected through VirtualBox port forwarding on ports 7010 and 7011 - see
Unreal Interface below.

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
|   +--------+-----+--------+--------+--------+--------+------+     |
|   |        |     |        |        |        |        |      |     |
| Start-   Auto- Power-   PDC-    Lights- Indicator Unreal- Unreal- |
| Sequence  Lock  train   Logic    Logic    Logic   Sender  Receiver|
|   |        |     |        |        |        |        |      |     |
|   +--------+-----+---+----+--------+--------+        |      |     |
|                      |                               |      |     |
|          vehicle_state (shared dict)                 |      |     |
|      is_locked / is_unlocked / driver_access /       |      |     |
|      is_ready / hazard_enabled                       |      |     |
+------------------------------------------------------|------|-----+
                                                        |      ^
       vehicle state, 12 fields, 50 Hz, TCP port 7010   |      |
                                                        |      |
                                                        |      |  measured speed, TCP port 7011
                                                        v      |
                            +------------- Unreal Engine -------------+
                            |  BP_Transceiver (TCP client, both ways) |
                            |    -> BPI_VSSVehicle (interface)        |
                            |         -> any vehicle blueprint        |
                            |            implementing the interface   |
                            |    -> WBP_Dashboard (speed, hazard)     |
                            +-----------------------------------------+
```

| Part | Runs where | Role |
|------|-----------|------|
| KUKSA Databroker | Docker container `Server` | single source of truth for all signals |
| KuksaConnection | VM, shared by all threads | thread-safe gRPC access |
| Logic modules | VM, one daemon thread each | read signals, decide, publish signals |
| vehicle_state | VM, shared dict | coordination between the modules |
| UnrealSender | VM, TCP server (7010) | streams the visualization state |
| UnrealReceiver | VM, TCP server (7011) | publishes the speed measured in Unreal |
| BP_Transceiver | Unreal | receives frames, sends interface messages |
| Vehicle blueprint | Unreal | implements BPI_VSSVehicle, renders the light states |

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
- unreal_sender.py - TCP bridge to the Unreal HMI (outbound)
- unreal_receiver.py - TCP return channel from Unreal (inbound)
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
- img/ - generated class and package diagrams

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
git clone https://github.com/saskiazie/sdv_logic.git && cd sdv_logic
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
[UnrealReceiver] Info: waiting for Unreal connection on port 7011
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
  - **0.02 s (fast lane)**: LightsLogic, IndicatorLogic, UnrealSender, UnrealReceiver - smooth blinking and frame rate
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
- `UnrealReceiver` acts as a TCP server on port 7011 and publishes the road speed
  measured by Unreal's physics engine - the only value in the system that
  originates outside the VM
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
  threshold_kmh: 15
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

### Where the Unreal project comes from

The visualization is **not** part of this repository - it lives on the Windows
host, while the logic runs in the VM. It was built from stock parts, so it can
be recreated without any purchased asset:

| Part | Origin |
|------|--------|
| Base project | Unreal Engine **Vehicle template** (Games -> Vehicle, Blueprint variant), shipped with every engine installation |
| Vehicle, level, camera | contained in that template - `Lvl_VehicleBasic`, the advanced vehicle pawn and its lighting components |
| TCP connection | a free Blueprint TCP socket plugin, providing the `Connect`, `Read String` nodes and the `OnMessageReceived` event |
| `BP_Transceiver`, `BPI_VSSVehicle`, `WBP_Dashboard` | written for this project |

The template was chosen deliberately over building a vehicle from scratch: the
logic produces **states**, not physics, so what was needed was a car whose
lights and motion can be driven from outside - not a driving simulation. The
template provides exactly that, including a drivable pawn whose Chaos physics
produce the road speed that `UnrealReceiver` reads back.

Two consequences worth knowing before rebuilding it:

- The **Blueprint** variant of the template is enough. The C++ variant needs a
  working Visual Studio toolchain and buys nothing here.
- Unreal on the host and the logic in the VM only meet through **VirtualBox
  port forwarding**. Both ports (7010 outbound, 7011 inbound) have to be
  forwarded to the VM, otherwise the plugin connects to nothing.

### Frame format (port 7010)

`UnrealSender` acts as a TCP server on port 7010. Unreal connects as a client and
receives ASCII frames at 50 Hz:

```
speed;gear;hazard;backup;drl;lowbeam;interior;pdc;turnl;turnr;gaspedal;steering|
30.00;127;0;0;1;0;0;999.0;1;0;0.35;-12.40|
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
| 10 | Vehicle.Chassis.Accelerator.PedalPosition | float (2 decimals) |
| 11 | Vehicle.Chassis.SteeringWheel.Angle | float (2 decimals) |

Fields 10 and 11 travel in a circle: Unreal reads the pedal and the wheel, the
values reach the broker, and the same values come back in the frame. The vehicle
is therefore driven by the signal, not by its own input - the databroker stays
the single source of truth even for values that originate in Unreal.

**Adding a field is a three-part change:** extend the frame in `unreal_sender.py`,
raise the `Length == 12` guard in `BP_Transceiver` to the new count, and add the
corresponding GET node. If the guard and the frame disagree, Unreal silently
discards *every* frame.

The frame stream can be inspected without Unreal using `test_files/test_unreal_client.py`.

### Return channel (port 7011)

`UnrealReceiver` is a second TCP server and receives one field from Unreal:

```
speed|
42.80|
```

| Index | Value | Type |
|-------|-------|------|
| 0 | measured road speed in km/h | float |

It publishes to `Vehicle.Speed` and is the sole writer of that signal. The
vehicle is moved by Unreal's Chaos physics, so the road actually reached only
exists there; without the return channel the VM would have to guess it from the
pedal position. The architecture rule is unaffected: Unreal sends a
**measurement**, not a decision.

Own port on purpose - sharing 7010 would mean parsing two directions on one
socket. Values are published only when they changed by more than 0.1 km/h, and
if several frames arrive at once only the newest is used; a backlog would lag
behind reality.

### Blueprint interface

`BP_Transceiver` drives the vehicle through the Blueprint interface
`BPI_VSSVehicle` - it holds no reference to a concrete vehicle class:

| Interface event | Frame index | Meaning |
|-----------------|-------------|---------|
| `VSS_SetHazard` | 2 | hazard lamps on/off |
| `VSS_SetLowBeam` | 5 | low beam on/off |
| `VSS_SetTurnLeft` | 8 | left indicator lamp on/off |
| `VSS_SetTurnRight` | 9 | right indicator lamp on/off |
| `VSS_SetThrottle` | 10 | accelerator pedal position (float) |

Speed (0) and hazard (2) additionally go to `WBP_Dashboard`, which is a widget
and not addressed through the interface.

`VSS_SetThrottle` deliberately carries the value to the vehicle instead of the
transceiver calling `Set Throttle Input` itself. The transceiver states *what*
the pedal position is; how the vehicle turns that into motion is its own
business. The input must be a **float** - a boolean input silently truncates
the pedal to on/off.

To connect a different vehicle: add `BPI_VSSVehicle` under Class Settings ->
Interfaces, implement the events, and wire them to whatever the vehicle uses to
show light or to drive (materials, light components, movement component). No
change in `BP_Transceiver` is required.

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
pyreverse -o svg -p SDV_Logic --colorized Logic_main.py kuksa_connection.py config_loader.py start_sequence.py auto_lock.py powertrain_safety_logic.py pdc_logic.py lights_logic.py indicator_logic.py unreal_sender.py unreal_receiver.py
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

