import socket
import time

class UnrealSender:
    '''
    Sends relevant vehicle states from KUKSA via TCP to the Unreal visualization. Output only - reads signals, never sets them.
    - Acts as a TCP server, Unreal connects as a client 
    - Sends ASCII format: field1;field2;...| (|= message terminator)    
    '''

    # Signals to be visualized 
    SPEED_SIGNAL = "Vehicle.Speed"
    GEAR_SIGNAL = "Vehicle.Powertrain.Transmission.CurrentGear"
    HAZARD_SIGNAL = "Vehicle.Body.Lights.Hazard.IsSignaling"
    BACKUP_SIGNAL = "Vehicle.Body.Lights.Backup.IsOn"
    DRL_SIGNAL = "Vehicle.Body.Lights.Running.IsOn"
    LOWBEAM_SIGNAL = "Vehicle.Body.Lights.Beam.Low.IsOn"
    INTERIOR_SGNAL = "Vehicle.Cabin.Light.AmbientLight.IsLightOn"
    PDC_SIGNAL = "Vehicle.ADAS.PDC.Rear.Distance"
    TURNL_SIGNAL = "Vehicle.Body.Lights.DirectionIndicator.Left.IsSignaling"
    TURNR_SIGNAL = "Vehicle.Body.Lights.DirectionIndicator.Right.IsSignaling"

    def __init__(self, kuksa, vehicle_state, host = "0.0.0.0", port = 7010):
        self.kuksa = kuksa
        self.vehicle_state = vehicle_state
        self.host = host 
        self.port = port

        # Prepare TCP server socket
        self.conn = None
        self.server = None
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.host, self.port))
            self.server.listen(1)
            self.server.setblocking(False) # non blocking (thread safe)
            print(f"UnrealSender: Waiting for Unreal connection on port {self.port}")

        except OSError as e:
            print(f"Unreal Sender: Port {self.port} already in use - deactivated UnrealSender")
            self.server = None

    def run(self):
        # 1. i fno connection yet: try to accept one 
        if self.server is None:
            return
                
        if self.conn is None:
            try:
                self.conn, addr = self.server.accept()
                self.conn.setblocking(False)
                print(f"UnrealSender: Unreal connected ({addr})")
            except BlockingIOError:
                return # no client yet, try again next cycle
            return

        # 2. Read values from KUKSa (read only)
        sigs = [self.SPEED_SIGNAL, self.GEAR_SIGNAL, self.HAZARD_SIGNAL, self.BACKUP_SIGNAL,
                self.DRL_SIGNAL, self.LOWBEAM_SIGNAL, self.INTERIOR_SGNAL, self.PDC_SIGNAL, self.TURNL_SIGNAL, self.TURNR_SIGNAL]
        try:
            vals = self.kuksa.get_many(sigs, default=None)
            speed = float(vals[self.SPEED_SIGNAL] or 0)
            gear = int(vals[self.GEAR_SIGNAL] or 126)
            hazard = bool(vals[self.HAZARD_SIGNAL] or False)
            backup = bool(vals[self.BACKUP_SIGNAL] or False)
            drl = bool(vals[self.DRL_SIGNAL] or False)
            lowbeam = bool(vals[self.LOWBEAM_SIGNAL] or False)
            interior = bool(vals[self.INTERIOR_SGNAL] or False)
            pdc = float(vals[self.PDC_SIGNAL] or 999.0)
            turnl = bool(vals[self.TURNL_SIGNAL] or False)
            turnr = bool(vals[self.TURNR_SIGNAL] or False)
        except Exception as e:
            print(f"UnrealSender Error while reading: {e}")
            return
        
        # 3. Build message (bools as 0/1 for easy parsing in Unreal)
        msg = (f"{speed:0.2f};{gear};{int(hazard)};{int(backup)};"
               f"{int(drl)};{int(lowbeam)};{int(interior)};{pdc:0.1f};{int(turnl)};{int(turnr)}|")
        
        # 4. Send - reset cleanly on connection loss
        try:
            self.conn.sendall(msg.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("UnrealSender: connection lost, waiting for new one")
            self.conn = None
            

if __name__== "__main__":
    import time
    from kuksa_connection import KuksaConnection
    kuksa = KuksaConnection("172.18.0.2", 55555)
    kuksa.connect()
    sender = UnrealSender(kuksa, None)
    while True:
        sender.run()
        time.sleep(0.05)            