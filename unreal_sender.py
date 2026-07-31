import socket
from kuksa_connection import KuksaConnection

class UnrealSender:
    '''
    Streams relevant vehicle states from KUKSA to the Unreal
    visualization via TCP. Output only - reads signals, never sets any.

    Purpose:
        Acts as the single bridge between the databroker and the HMI.
        Unreal contains no logic; it only parses and displays this
        stream (architecture rule: all logic lives in the VM).

    Input signals (frame field order!):
        0  Vehicle.Speed
        1  Vehicle.Powertrain.Transmission.CurrentGear
        2  Vehicle.Body.Lights.Hazard.IsSignaling
        3  Vehicle.Body.Lights.Backup.IsOn
        4  Vehicle.Body.Lights.Running.IsOn
        5  Vehicle.Body.Lights.Beam.Low.IsOn
        6  Vehicle.Cabin.Light.AmbientLight.IsLightOn
        7  Vehicle.ADAS.PDC.Rear.Distance
        8  Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling
        9  Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling
        10 Vehicle.Chassis.Accelerator.PedalPosition
        11 Vehicle.Chassis.SteeringWheel.Angle 

    Output signals:
        none in KUKSA - TCP ASCII frames to Unreal:
        "speed;gear;hazard;backup;drl;lowbeam;interior;pdc;turnl;turnr;gaspedal;steering|"
        (bools as 0/1, "|" = message terminator)

    Notes:
        - Acts as TCP server (default port 7010), Unreal connects as
          client. Non-blocking accept: the thread never stalls.
        - TCP_NODELAY disables Nagle's algorithm: the small frames are
          sent immediately instead of being batched by the OS, which
          would distort the blink timing in the visualization.
        - The field count MUST match the Length==12 guard in
          BP_Transceiver2. Adding a field means: extend this frame,
          set the guard to the new count and add the GET in Unreal -
          all in one step, otherwise every frame is discarded.
        - All twelve signals are read in ONE get_many() call to keep the
          lock contention on the shared connection low (fast lane).
    '''

    # Input signal paths (order = frame field order)
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"
    BACKUP_SIGNAL = "Vehicle.Body.Lights.Backup.IsOn"
    DRL_SIGNAL = "Vehicle.Body.Lights.Running.IsOn"
    LOWBEAM_SIGNAL = "Vehicle.Body.Lights.Beam.Low.IsOn"
    INTERIOR_SIGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn"
    PDC_SIGNAL = "Vehicle.ADAS.PDC.Rear.Distance"
    TURNL_SIGNAL = "Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling"
    TURNR_SIGNAL = "Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling"
    GASPEDAL_SIGNAL = "Vehicle.Chassis.Accelerator.PedalPosition"
    STEERING_SIGNAL = "Vehicle.Chassis.SteeringWheel.Angle"

    def __init__(self, kuksa: KuksaConnection, vehicle_state, host="0.0.0.0", port=7010):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state
        self.host = host
        self.port = port

        # prepare the TCP server socket
        self.conn = None
        self.server = None
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET,
                                   socket.SO_REUSEADDR, 1)
            self.server.bind((self.host, self.port))
            self.server.listen(1)
            self.server.setblocking(False)  # non-blocking accept
            print(f"[UnrealSender] Info: waiting for Unreal connection "
                  f"on port {self.port}")
        except OSError:
            print(f"[UnrealSender] Error: port {self.port} already in "
                  f"use - UnrealSender deactivated")
            self.server = None

    def run(self):
        if self.server is None:
            return

        # 1. no connection yet: try to accept one (non-blocking)
        if self.conn is None:
            try:
                self.conn, addr = self.server.accept()
                self.conn.setblocking(False)
                # disable Nagle's algorithm for undistorted frame timing
                self.conn.setsockopt(socket.IPPROTO_TCP,
                                     socket.TCP_NODELAY, 1)
                print(f"[UnrealSender] Info: Unreal connected ({addr})")
            except BlockingIOError:
                return  # no client yet, try again next cycle
            return

        # 2. read all values from KUKSA in one gRPC call (read only)
        sigs = [self.SPEED_SIGNAL, self.GEAR_SIGNAL, self.HAZARD_SIGNAL,
                self.BACKUP_SIGNAL, self.DRL_SIGNAL, self.LOWBEAM_SIGNAL,
                self.INTERIOR_SIGNAL, self.PDC_SIGNAL,
                self.TURNL_SIGNAL, self.TURNR_SIGNAL, self.GASPEDAL_SIGNAL, self.STEERING_SIGNAL]
        try:
            vals = self.kuksa.get_many(sigs, default=None)
            speed = float(vals[self.SPEED_SIGNAL] or 0)
            gear = int(vals[self.GEAR_SIGNAL] or 126)
            hazard = bool(vals[self.HAZARD_SIGNAL] or False)
            backup = bool(vals[self.BACKUP_SIGNAL] or False)
            drl = bool(vals[self.DRL_SIGNAL] or False)
            lowbeam = bool(vals[self.LOWBEAM_SIGNAL] or False)
            interior = bool(vals[self.INTERIOR_SIGNAL] or False)
            pdc = float(vals[self.PDC_SIGNAL] or 999.0)
            turnl = bool(vals[self.TURNL_SIGNAL] or False)
            turnr = bool(vals[self.TURNR_SIGNAL] or False)
            gaspedal = float(vals[self.GASPEDAL_SIGNAL] or 0.0)
            steering = float(vals[self.STEERING_SIGNAL] or 0.0)
        except Exception as e:
            print(f"[UnrealSender] Error: reading from broker failed: {e}")
            return

        # 3. build the message (bools as 0/1 for easy parsing in Unreal)
        msg = (f"{speed:0.2f};{gear};{int(hazard)};{int(backup)};"
               f"{int(drl)};{int(lowbeam)};{int(interior)};{pdc:0.1f};"
               f"{int(turnl)};{int(turnr)};{gaspedal:0.2f};{steering:0.2f}|")

        # 4. send - reset cleanly on connection loss
        try:
            self.conn.sendall(msg.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("[UnrealSender] Info: connection lost, waiting for "
                  "a new one")
            self.conn = None


if __name__ == "__main__":
    # standalone test: stream directly without the other logic modules
    # (adjust host/port to your databroker if needed)
    import time
    from kuksa_connection import KuksaConnection

    kuksa = KuksaConnection("172.18.0.2", 55555)
    kuksa.connect()
    sender = UnrealSender(kuksa, None)
    while True:
        sender.run()
        time.sleep(0.05)