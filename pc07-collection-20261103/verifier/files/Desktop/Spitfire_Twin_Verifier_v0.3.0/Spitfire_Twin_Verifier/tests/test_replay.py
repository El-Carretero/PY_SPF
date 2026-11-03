from dataclasses import replace
import socket
import time
import unittest

from spitfire_twin_verifier.evidence import EvidenceError
from spitfire_twin_verifier.replay import ReplayServer
from test_evidence import item, snapshot


class ReplayTests(unittest.TestCase):
    def client(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1',0))
        sock.settimeout(.12)
        self.addCleanup(sock.close)
        return sock

    def test_loopback_only(self):
        for addr in ('0.0.0.0','10.19.70.13','localhost','::1'):
            with self.assertRaises(EvidenceError):
                ReplayServer(snapshot(item()),'left',bind_ip=addr)

    def test_exact_match_and_mismatch(self):
        row=item()
        sock=self.client()
        with ReplayServer(snapshot(row),'left') as server:
            sock.sendto(b'wrong',server.local_address)
            with self.assertRaises(socket.timeout):sock.recvfrom(4096)
            self.assertEqual(server.status()['matched_datagrams'],0)
            sock.sendto(bytes.fromhex(row.request_hex),server.local_address)
            self.assertEqual(sock.recvfrom(4096)[0],bytes.fromhex(row.response_hex))
            self.assertTrue(server.status()['complete'])
            self.assertEqual(server.status()['mismatches'],1)

    def test_drop_preserved_and_peer_isolation(self):
        first=item(status='DROPPED',response_hex='',response_value=None)
        second=item(2)
        sock,other=self.client(),self.client()
        with ReplayServer(snapshot(first,second),'left') as server:
            sock.sendto(bytes.fromhex(first.request_hex),server.local_address)
            with self.assertRaises(socket.timeout):sock.recvfrom(4096)
            self.assertEqual(server.status()['matched_datagrams'],1)
            other.sendto(bytes.fromhex(second.request_hex),server.local_address)
            with self.assertRaises(socket.timeout):other.recvfrom(4096)
            self.assertEqual(server.status()['matched_datagrams'],1)
            sock.sendto(bytes.fromhex(second.request_hex),server.local_address)
            self.assertEqual(sock.recvfrom(4096)[0],bytes.fromhex(second.response_hex))
            self.assertEqual(server.status()['rejected_peers'],1)

    def test_missing_or_corrupted_capture_rejected(self):
        captures=[snapshot(),snapshot(item(),pending=({'x':1},)),snapshot(item(status='STOPPED')),
                  snapshot(item(command_id=1099)),snapshot(item(command_index=2)),snapshot(item(response_hex=''))]
        for captured in captures:
            with self.assertRaises(EvidenceError):ReplayServer(captured,'left')

    def test_extra_packet_has_no_reply(self):
        row=item()
        sock=self.client()
        with ReplayServer(snapshot(row),'left') as server:
            for index in range(2):
                sock.sendto(bytes.fromhex(row.request_hex),server.local_address)
                if index==0:sock.recvfrom(4096)
                else:
                    with self.assertRaises(socket.timeout):sock.recvfrom(4096)
            self.assertEqual(server.status()['events'][-1]['status'],'EXTRA_REQUEST')
