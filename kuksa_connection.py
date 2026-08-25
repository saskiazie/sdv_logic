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
        - The logic modules write through write() / write_many(), not
          through publish() / set() directly. Whether a signal is
          written as a current or as a target value is configured in
          config/writemode_config.yaml.
    '''

    def __init__(self, host="127.0.0.1", port=55555, write_mode=None):
        # host/port fall back to local defaults if not configured
        self.client = VSSClient(host, port)
        self._lock = threading.Lock()

        # Write mode table, see write() below. Without a configuration
        # every signal falls back to "publish", which reproduces the
        # behaviour of the broker-only setup exactly.
        write_mode = write_mode or {}
        self.default_write_mode = write_mode.get("default", "publish")
        self.signal_write_mode = write_mode.get("signals", {}) or {}

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

    # ------------------------------------------------------------------
    # Mode-aware writing
    # ------------------------------------------------------------------
    # The logic modules do not decide HOW a signal is written, only THAT
    # it is written. Which of the two KUKSA write paths is used is a
    # property of the signal, not of the module:
    #
    #   publish  -> current value. The logic itself is the provider;
    #               nothing behind the broker owns this signal.
    #   actuate  -> target value. A control unit owns the signal and
    #               takes the request via the vss2dbc mapping.
    #
    # The mapping lives in config/writemode_config.yaml, so the whole
    # system switches between the broker-only setup and the wired
    # demonstrator without touching a single logic module.
    #
    # Constraint: "actuate" is only valid for VSS nodes of type
    # actuator. Sensor nodes have no target value; a request would be
    # rejected by the broker. This is why signals such as CurrentGear
    # or Vehicle.Speed cannot simply be switched over.

    def mode_of(self, signal):
        '''Return the configured write mode for one signal.'''
        return self.signal_write_mode.get(signal, self.default_write_mode)

    def write(self, signal, value):
        '''Write one value using the mode configured for that signal.'''
        if self.mode_of(signal) == "actuate":
            self.set(signal, value)
        else:
            self.publish(signal, value)

    def write_many(self, values):
        '''Write several values using their configured modes.

        Signals sharing a mode are bundled into ONE gRPC call, so
        atomicity is preserved within a mode group. Signals that must
        never drift apart (e.g. left/right indicator lights) therefore
        have to share the same mode - they do, because they share a
        control unit.
        '''
        current = {}
        target = {}
        for signal, value in values.items():
            if self.mode_of(signal) == "actuate":
                target[signal] = value
            else:
                current[signal] = value

        if current:
            self.publish_many(current)
        if target:
            with self._lock:
                self.client.set_target_values(
                    {s: Datapoint(value=v) for s, v in target.items()}
                )