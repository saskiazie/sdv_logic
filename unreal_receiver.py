import socket
from kuksa_connection import KuksaConnection


class UnrealReceiver:
    '''
    Receives measured values from the Unreal visualization and publishes
    them to KUKSA. Input only - writes signals, never reads any.

    Purpose:
        Counterpart to UnrealSender. Since the vehicle is moved by the
        Chaos physics engine, the actual road speed only exists inside
        Unreal. Without this return channel there would be two competing
        truths: the value derived from the pedal in the VM and the speed
        the vehicle really reaches. This module makes the simulated
        vehicle a signal source like any other sensor.

        The architecture rule still holds: Unreal sends MEASUREMENTS and
        REQUESTS, never computed states. It reports how fast it is - it
        does not decide whether the car should lock its doors. That
        decision stays in the logic modules, which simply read the
        signal published here.

    Input signals:
        none in KUKSA - TCP ASCII frames from Unreal:
        "speed|"
        ("|" = message terminator, same format as UnrealSender)

        Frame field order:
        0  measured road speed in km/h (float)

    Output signals:
        Vehicle.Speed

    Notes:
        - Acts as TCP server (default port 7011), Unreal connects as
          client. Non-blocking accept and recv: the thread never stalls.
        - Own port on purpose. Sharing port 7010 with the sender would
          mean parsing two directions on one socket; a separate server
          keeps both modules independent and individually testable.
        - TCP is a byte STREAM, not a message queue. Frames may arrive
          fragmented or several at once, so incoming data is buffered
          and split on "|". Only the LAST complete frame is used, older
          ones are discarded - the newest measurement is the only
          relevant one and a backlog would lag behind reality. This is
          the same two-stage parsing BP_Transceiver2 does in the other
          direction.
        - Incomplete frames are kept in the buffer for the next cycle.
          The buffer is capped (MAX_BUFFER): if no terminator arrives
          the sender is broken, and an unbounded buffer would slowly
          eat memory.
        - The field count MUST match what Unreal sends. Adding a field
          means: extend the frame in Unreal, raise EXPECTED_FIELDS here
          and add the parsing - all in one step, otherwise every frame
          is discarded.
        - Values are only published when they changed by more than
          SPEED_EPSILON. At a 20 Hz cycle an unconditional publish would
          put ~20 writes per second on the broker for a value that is
          usually constant.
        - Sole writer of Vehicle.Speed: no logic module publishes this
          signal (AutoLock and PowertrainSafety only read it, and the
          latter deliberately no longer overwrites sensor values). The
          only other write is the baseline reset to 0.0 in
          init_kuksa_signals.py at startup. Ownership is therefore
          unambiguous - Unreal measures, the logic reads.
    '''

    # Output signal path (order = frame field order)
    SPEED_SIGNAL = "Vehicle.Speed"

    # frame format contract with Unreal
    EXPECTED_FIELDS = 1
    TERMINATOR = "|"

    # only publish once the value really moved (km/h)
    SPEED_EPSILON = 0.1

    # a frame without terminator larger than this means a broken sender
    MAX_BUFFER = 4096

    def __init__(self, kuksa: KuksaConnection, vehicle_state,
                 host="0.0.0.0", port=7011):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state
        self.host = host
        self.port = port

        # holds incomplete frames between cycles (TCP is a stream)
        self.buffer = ""
        # last published value, used for the change detection
        self.last_speed = None

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
            print(f"[UnrealReceiver] Info: waiting for Unreal connection "
                  f"on port {self.port}")
        except OSError:
            print(f"[UnrealReceiver] Error: port {self.port} already in "
                  f"use - UnrealReceiver deactivated")
            self.server = None

    def _reset_connection(self, reason):
        # drop the client and start over - a half-read frame from the
        # old connection must not leak into the next one
        print(f"[UnrealReceiver] Info: {reason}, waiting for a new "
              f"connection")
        self.conn = None
        self.buffer = ""

    def run(self):
        if self.server is None:
            return

        # 1. no connection yet: try to accept one (non-blocking)
        if self.conn is None:
            try:
                self.conn, addr = self.server.accept()
                self.conn.setblocking(False)
                self.conn.setsockopt(socket.IPPROTO_TCP,
                                     socket.TCP_NODELAY, 1)
                print(f"[UnrealReceiver] Info: Unreal connected ({addr})")
            except BlockingIOError:
                return  # no client yet, try again next cycle
            return

        # 2. read whatever is available (non-blocking)
        try:
            data = self.conn.recv(4096)
            if not data:
                # empty read means the peer closed the connection
                self._reset_connection("connection closed by Unreal")
                return
            self.buffer += data.decode("utf-8", errors="ignore")
        except BlockingIOError:
            return  # nothing new this cycle, not an error
        except (ConnectionResetError, OSError) as e:
            self._reset_connection(f"connection lost ({e})")
            return

        # 3. guard against a sender that never terminates a frame
        if len(self.buffer) > self.MAX_BUFFER:
            print("[UnrealReceiver] Error: no frame terminator found - "
                  "buffer discarded (check the frame format in Unreal)")
            self.buffer = ""
            return

        # 4. split into frames; the tail after the last "|" is an
        #    incomplete frame and stays in the buffer for next time
        if self.TERMINATOR not in self.buffer:
            return
        parts = self.buffer.split(self.TERMINATOR)
        self.buffer = parts[-1]

        # only the newest complete frame matters - a backlog of old
        # measurements would make the visualization lag behind reality
        frames = [f for f in parts[:-1] if f.strip()]
        if not frames:
            return
        frame = frames[-1]

        # 5. parse - a fragment is discarded instead of parsed wrongly
        fields = frame.split(";")
        if len(fields) < self.EXPECTED_FIELDS:
            print(f"[UnrealReceiver] Error: expected "
                  f"{self.EXPECTED_FIELDS} fields, got {len(fields)} "
                  f"- frame discarded")
            return
        try:
            speed = float(fields[0])
        except ValueError:
            print(f"[UnrealReceiver] Error: field 0 is not a number: "
                  f"'{fields[0]}' - frame discarded")
            return

        # 6. publish only on real change (keeps broker load low)
        if (self.last_speed is None
                or abs(speed - self.last_speed) > self.SPEED_EPSILON):
            try:
                # Deliberately publish(), not write(): Vehicle.Speed is
                # of type sensor and is fed from CAN on the wired
                # demonstrator - see writemode_config.yaml.
                self.kuksa.publish(self.SPEED_SIGNAL, speed)
                self.last_speed = speed
            except Exception as e:
                print(f"[UnrealReceiver] Error: publishing to broker "
                      f"failed: {e}")


if __name__ == "__main__":
    # standalone test: receive directly without the other logic modules
    # (adjust host/port to your databroker if needed)
    import time
    from kuksa_connection import KuksaConnection

    kuksa = KuksaConnection("172.18.0.2", 55555)
    kuksa.connect()
    receiver = UnrealReceiver(kuksa, None)
    while True:
        receiver.run()
        time.sleep(0.05)