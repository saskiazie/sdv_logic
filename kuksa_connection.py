import threading
from kuksa_client.grpc import VSSClient, Datapoint

class KuksaConnection:
        def __init__(self, host="127.0.0.1", port=55555): # fallback, if no values have been configurated (in config file)
                self.client = VSSClient(host, port)
                self._lock = threading.Lock()

        def connect(self):
                try: 
                        self.client.connect()
                        print("Kuksa sucessfully connected")
                        return True
                except Exception as e:
                        print("Kuksa connection failed:", e)
                        return False

        def get(self, signal, default=None):
                with self._lock:
                        result = self.client.get_current_values([signal])
                datapoint = result.get(signal)
                return getattr(datapoint, "value", default)

        def set(self, signal, value):
                with self._lock:
                        self.client.set_target_values({signal: Datapoint(value=value)})                

        def publish(self, signal, value):
                with self._lock:
                        self.client.set_current_values({signal: Datapoint(value=value)})

        def get_many(self, signals, default=None):
                with self._lock:
                        result = self.client.get_current_values(signals)
                return {signal: getattr(result.get(signal), "value", default) for signal in signals}        
        
        def publish_many(self, values):
                with self._lock:
                        self.client.set_current_values({signal: Datapoint(value=value) for signal, value in values.items()})