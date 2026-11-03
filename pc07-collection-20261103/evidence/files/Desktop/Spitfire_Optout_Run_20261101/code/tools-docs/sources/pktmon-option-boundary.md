# Actual Pktmon pcapng option-boundary regression

The 408-byte `evidence/preflight.pcapng` contains two Enhanced Packet Blocks and
a final 36-byte Interface Statistics Block at byte 372. The statistics block has
one `isb_ifdrop` option (code 5, length 8, value 0), ending exactly at the block
body boundary without an explicit `opt_endofopt` record.

The initial converter incorrectly required that record. The IETF pcapng draft
requires readers to check the enclosing block boundary and accept a complete
option list that ends there. The converter now implements this reader behavior
while still rejecting partial option headers, partial option values, invalid
option sizes and mismatched enclosing block lengths.

Source: [IETF pcapng draft 06, options](https://datatracker.ietf.org/doc/draft-ietf-opsawg-pcapng/06/).

The actual input remains unchanged. Conversion and independent `dpkt 1.9.8`
reopening confirm two Ethernet packets of 87 and 80 bytes, UDP payloads of 45
and 38 bytes, and one guest request / simulator response pair. The simulator
response contains `<1068>0`. This is guest diagnostic-code traffic, not evidence
of the original Spitfire executable's traffic.

The recorded drop counter is zero. This counter and a successful two-packet
probe do not establish completeness of a future long-running capture.

Validation: all 14 converter tests passed, including the actual Pktmon
regression, exact input/output Ethernet-byte and timestamp comparison through
independent `dpkt` readers, malformed boundaries and missing packet bytes.
