import socket

# Connect to the UnrealSender running inside the VM
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(("127.0.0.1", 7010))
print("Connected to UnrealSender, reiceiving data...\n")

buffer = ""
try:
    while True:
        data = client.recv(256).decode("utf-8")
        if not data:
            break
        buffer += data

        # Split on the message terminator '|'
        while "|" in buffer:
            msg, buffer = buffer.split("|", 1)
            print("Received:", msg)

except KeyboardInterrupt:
    print("\nTest client stopped")

finally:
    client.close()
