import threading

from kuksa_client.grpc import VSSClient, Datapoint

class KuksaConnection:
    '''
    Thread-safe wrapper around the KUKSA databroker client.

    Purpose:
        Provides the single shared connection to the KUKSA databroker
        for all logic modules. The underlying VSSClient is NOT
        thread-safe, therefore every gRPC call is serialized with a
        lock. Without the lock, concurrent calls from the module
        threads can silently block each other for hundreds of
        milliseconds (observed as skipped indicator in unreal toggles).

    Input signals:
        none (transport layer only)

    Output signals:
        none (transport layer only)

    Notes:
        - get_many() / publish_many() bundle several signals into ONE
          gRPC call. Prefer them in fast-cycle modules (0.02 s lane):
          fewer calls mean less lock contention.
        - publish_many() is atomic on the broker side: all values
          become visible at the same moment. Required for signals that
          must never drift apart (e.g. left/right indicator lights).
    '''

    def __init__(self, host="127.0.0.1", port=55555):
        # host/port fall back to local defaults if not configured
        self.client = VSSClient(host, port)
        self._lock = threading.Lock()

    def connect(self):
        '''Open the gRPC connection. Returns True on success.'''
        try:
            self.client.connect()
            print("[KuksaConnection] Info: successfully connected")
            return True
        except Exception as e:
            print(f"[KuksaConnection] Error: connection failed: {e}")
            return False

    def get(self, signal, default=None):
        '''Read one current value. Returns default if the signal is unset.'''
        with self._lock:
            result = self.client.get_current_values([signal])
        datapoint = result.get(signal)
        return getattr(datapoint, "value", default)

    def get_many(self, signals, default=None):
        '''Read several current values in ONE gRPC call. Returns a dict.'''
        with self._lock:
            result = self.client.get_current_values(signals)
        return {s: getattr(result.get(s), "value", default) for s in signals}

    def set(self, signal, value):
        '''Write one target value (actuator request).'''
        with self._lock:
            self.client.set_target_values({signal: Datapoint(value=value)})

    def publish(self, signal, value):
        '''Write one current value (sensor / actual state).'''
        with self._lock:
            self.client.set_current_values({signal: Datapoint(value=value)})

    def publish_many(self, values):
        '''Write several current values in ONE atomic gRPC call.

        values: dict {signal_path: value}
        '''
        with self._lock:
            self.client.set_current_values(
                {signal: Datapoint(value=v) for signal, v in values.items()}
            )