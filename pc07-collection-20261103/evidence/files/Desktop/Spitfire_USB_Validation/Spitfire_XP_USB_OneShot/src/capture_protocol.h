#ifndef CAPTURE_PROTOCOL_H
#define CAPTURE_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>
#define CAP_MAX_PAIRS 64
#define CAP_COMMAND 1
#define CAP_RESPONSE 2
/* Pure decoding only: never constructs or sends network traffic. IPv4 values
   are in human-readable (big endian) numeric order, independent of CPU order. */
typedef struct {
 uint32_t src_ip, dst_ip;
 uint16_t src_port, dst_port;
 const unsigned char *payload;
 uint32_t payload_len;
 unsigned kind, tag, write_commands, first_write_tag, malformed_command;
} cap_packet;
typedef struct {
 uint32_t client_ip, controller_ip;
 uint16_t client_port, controller_port;
 unsigned interface_id, commands, responses;
 uint32_t last_command_ms, last_response_ms;
} cap_pair;
typedef struct {
 cap_pair pairs[CAP_MAX_PAIRS];
 unsigned pair_count, pair_overflow, command_packets, response_packets;
 unsigned any_write_commands, first_write_tag, malformed_commands;
} cap_observation;
/* Returns 1 only for a complete, unfragmented IPv4 UDP frame using port1024.
   Other or incomplete frames remain in the PCAP, but cannot establish readiness. */
int cap_decode_ethernet(const unsigned char *frame, size_t length, cap_packet *packet);
void cap_observe(cap_observation *obs, const cap_packet *p, unsigned interface_id,
                 int source_is_local, int destination_is_local, uint32_t now_ms);
/* 1=unique recent bidirectional pair. Writes/malformed commands permanently
   disqualify UI readiness. Adapter/IO failures are checked by the caller. */
int cap_pair_ready(const cap_observation *obs, uint32_t now_ms);
#endif
