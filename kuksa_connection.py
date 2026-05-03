from kuksa_client.grpc import VSSClient, Datapoint

class KuksaConnection:
        def __init__(self, host="127.0.0.1", port=55555):
                self.client = VSSClient(host, port)

        def connect(self):
                try: 
                        self.client.connect()
                        print("Kuksa sucessfully connected")
                        return True
                except Exception as e:
                        print("Kuksa connection failed:", e)
                        return False

        def get(self, signal, default=None):
                result = self.client.get_current_values([signal])
                datapoint = result.get(signal)
                return getattr(datapoint, "value", default)

        def set(self, signal, value):
                self.client.set_target_values({signal: Datapoint(value=value)})                

        def publish(self, signal, value):
                self.client.set_current_values({
                        signal: Datapoint(value=value)
                })