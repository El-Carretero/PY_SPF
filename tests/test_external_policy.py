"""Outbound boundaries must remain independent of any Empower hardware."""
import unittest

from spitfire.external_policy import RESET_COMMAND_IDS, query_allowed, validate_request
from spitfire.protocol import COMMANDS, QUERIES
from spitfire.scheduling import Request, Scheduler


class OutboundPolicyTests(unittest.TestCase):
    def test_entire_original_pump_catalog_is_rejected(self):
        for tag, text in {**QUERIES, **COMMANDS}.items():
            if text.startswith(('EMP:', 'MIL:')):
                with self.subTest(tag=tag, text=text):
                    self.assertFalse(query_allowed(tag))
                    with self.assertRaises(PermissionError):
                        Scheduler().push(tag)
                    with self.assertRaises(PermissionError):
                        _ = Request(tag).message

    def test_global_on_off_and_raw_paths_cannot_reach_wire(self):
        for tag, parameter in ((2027,''),(2028,''),(2034,'EMP:ON'),(2054,''),(2055,'')):
            with self.subTest(tag=tag):
                with self.assertRaises((PermissionError, ValueError)):
                    _ = Request(tag, parameter).message

    def test_board_opt_out_is_explicit_and_one_way(self):
        self.assertEqual(Request(1068).message, '[1068]EMPOPTOUT?')
        self.assertEqual(Request(2036,' 1').message, '[2036]EMPOPTOUT 1')
        with self.assertRaises(PermissionError):
            validate_request(2036,' 0')
        self.assertNotIn(2044,RESET_COMMAND_IDS)
        for tag in RESET_COMMAND_IDS:
            validate_request(tag)

    def test_structured_arguments_cannot_inject_commands(self):
        attempts=(
            ' 1 ON\n[2005]EMP:ON', ' 1 ON\rOFF', ' 1 ON;EMP:ON',
            ' 1 ON\0', ' 1 ON,[2005]', ' 1 ON\t', ' 1 ONé', '1 ON',
        )
        for argument in attempts:
            with self.subTest(argument=argument),self.assertRaises(ValueError):
                _ = Request(2019,argument).message
        with self.assertRaises(ValueError):
            validate_request(1038,' 1')

    def test_protection_and_numeric_guards(self):
        for tag,argument in ((2019,' 1 NBWD'),(2019,' 2 NENA'),(2024,' 1'),(2029,' 1'),(2035,' 1'),(2053,' 1')):
            with self.subTest(tag=tag,argument=argument),self.assertRaises(PermissionError):
                validate_request(tag,argument)
        for tag,argument in ((2019,' 1 nan'),(2019,' 1 1001'),(2019,' 0 ON'),(2025,' inf'),(2025,' -1'),(2020,' 0'),(2020,' 1.5'),(2014,' 1e999')):
            with self.subTest(tag=tag,argument=argument),self.assertRaises(ValueError):
                validate_request(tag,argument)
        for tag,argument in ((2019,' 1 ON'),(2019,' 2 off'),(2019,' 1 12.50'),(2019,' 5 BWD'),(2019,' 2 ENA'),(2020,' 2.00')):
            validate_request(tag,argument)


class StopSchedulingTests(unittest.TestCase):
    def test_stop_cancels_unsent_on_and_runs_before_readbacks(self):
        scheduler=Scheduler()
        scheduler.push(1038)
        scheduler.next_request()
        scheduler.push(2019,' 2 ON')
        scheduler.push(2025,' 1000')
        scheduler.push(1030,inside=False)
        scheduler.queue_stop()
        self.assertEqual([(r.tag,r.parameter) for r in scheduler.urgent],[(2019,' 1 OFF'),(2019,' 2 OFF')])
        self.assertFalse(scheduler.inside)
        self.assertIsNone(scheduler.next_request())
        scheduler.acknowledge(1038)
        self.assertEqual(scheduler.next_request().parameter,' 1 OFF')
        scheduler.acknowledge(2019)
        self.assertEqual(scheduler.next_request().parameter,' 2 OFF')
        scheduler.acknowledge(2019)
        self.assertEqual(scheduler.next_request().tag,1030)

    def test_repeat_stop_does_not_duplicate_queued_or_inflight_offs(self):
        scheduler=Scheduler()
        scheduler.queue_stop()
        scheduler.queue_stop()
        self.assertEqual(len(scheduler.urgent),2)
        scheduler.next_request()
        scheduler.queue_stop()
        self.assertEqual(len(scheduler.urgent),1)
        self.assertEqual(scheduler.urgent[0].parameter,' 2 OFF')

    def test_timeout_releases_without_replaying_write_and_preserves_second_off(self):
        scheduler=Scheduler()
        scheduler.queue_stop(include_hv=True)
        scheduler.next_request()
        timed_out=scheduler.abandon_inflight()
        self.assertEqual(timed_out.parameter,' 1 OFF')
        self.assertEqual(scheduler.next_request().parameter,' 2 OFF')
        scheduler.acknowledge(2019)
        self.assertEqual(scheduler.next_request().tag,2016)

    def test_urgent_rejects_enabling_commands(self):
        with self.assertRaises(ValueError):
            Scheduler().push_urgent(2019,' 1 ON')

    def test_revalidation_prevents_direct_queue_bypass(self):
        scheduler=Scheduler()
        scheduler.inside.append(Request(2044))
        with self.assertRaises(PermissionError):
            scheduler.next_request(auto_poll=False)
        self.assertEqual(scheduler.balance,0)


if __name__ == '__main__':
    unittest.main()
