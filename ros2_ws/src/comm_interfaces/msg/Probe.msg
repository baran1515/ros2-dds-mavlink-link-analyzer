# Link probe message used to measure round-trip time and loss over DDS.
uint32 seq                         # incremented by the sender for every probe
builtin_interfaces/Time stamp      # sender clock at publish time
uint8[] payload                    # padding to emulate telemetry message sizes
