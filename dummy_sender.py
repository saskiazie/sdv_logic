import socket
import time
import math 

# standalone test sender mimics UnrealSender output wihtout needing KUKSA
HOST = "0.0.0.0"
PORT = 7010

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(1)
print(f"DummySender: Waiting for connection on port {PORT}...")

conn, addr = server.accept()
print(f"DummySender: Connected ({addr})")

t = 0.0
try:
    while True:
        # Fake values that change over time so you can see motion in Unreal
        speed = abs(math.sin(t*0.2))*80 # 0...80km/h oscillating
        gear = 127 # drive
        hazard = 1 if int(t) % 4 < 2 else 0 # blinks every ~2s
        backup = 0
        drl = 1
        lowbeam = 0
        interior = 0
        pdc = 999.0

        msg =(f"{speed:.2f};{gear};{hazard};{backup};"
              f"{drl};{lowbeam};{interior};{pdc:.1f}|")
        
        conn.sendall(msg.encode("utf-8"))
        print("Sent:", msg)

        t += 0.1
        time.sleep(0.1) # 10 Hz

except (BrokenPipeError, ConnectionResetError, KeyboardInterrupt):
    print("DummySender: stopped")

finally:
    conn.close()
    server.close()