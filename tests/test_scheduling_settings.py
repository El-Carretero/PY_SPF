import tempfile
from pathlib import Path
import unittest
from spitfire.scheduling import Scheduler, StartupAttempts
from spitfire.external_policy import REQUIRED_READBACKS
from spitfire.settings import AccessKeySequence, read_max_level, access_allowed, append_datalog


class IndependentSchedulingTests(unittest.TestCase):
    def test_initialization_has_no_pump_requests_or_automatic_writes(self):
        queue = Scheduler(); queue.queue_initial()
        messages = []
        while queue.inside:
            request = queue.next_request(auto_poll=False)
            messages.append(request)
            queue.acknowledge(request.tag)
        self.assertEqual([r.tag for r in messages[:8]], [1069, 1068, 1087, 1033, 1038, 1037, 1032, 1057])
        self.assertEqual(messages[-1].tag, 1062)
        self.assertTrue(all(r.tag < 2000 for r in messages))
        self.assertFalse(any('EMP:' in r.message or 'MIL:' in r.message for r in messages))
        self.assertTrue(set(REQUIRED_READBACKS).issubset(r.tag for r in messages))

    def test_priority_and_acknowledgement(self):
        queue = Scheduler();queue.push(1030, inside=False);queue.push(1038)
        self.assertEqual(queue.next_request().tag, 1038)
        self.assertIsNone(queue.next_request())
        queue.acknowledge(1038)
        self.assertEqual(queue.next_request().tag, 1030)

    def test_user_and_service_poll_cycles(self):
        queue=Scheduler();queue.queue_poll()
        user_tags = {r.tag for r in queue.outside}
        self.assertTrue(set(REQUIRED_READBACKS).issubset(user_tags))
        self.assertFalse(any('EMP:' in r.message or 'MIL:' in r.message for r in queue.outside))
        queue.clear();queue.access_level=1;queue.queue_poll()
        service_tags = {r.tag for r in queue.outside}
        self.assertTrue(user_tags.issubset(service_tags))
        self.assertTrue({1055, 1056}.issubset(service_tags))

    def test_unrelated_reply_does_not_release_outstanding_request(self):
        now=[1.0];queue=Scheduler(clock=lambda:now[0])
        queue.push(1038);queue.push(1030)
        queue.next_request()
        now[0]=2.0
        self.assertFalse(queue.acknowledge(1013))
        self.assertFalse(queue.acknowledge(1000))
        self.assertEqual(queue.last_received,1.0)
        self.assertIsNone(queue.next_request())
        self.assertTrue(queue.acknowledge(1038))
        self.assertEqual(queue.next_request().tag,1030)

    def test_legacy_status_reset_request_is_not_a_polling_write(self):
        queue=Scheduler();queue.reset_channels_pending=True;queue.queue_poll()
        self.assertTrue(all(r.tag<2000 for r in queue.outside))
        self.assertFalse(queue.reset_channels_pending)

    def test_emp_subsystem_reinitialization_sends_nothing(self):
        queue=Scheduler();queue.queue_subsystem_initial('emp')
        self.assertIsNone(queue.next_request(auto_poll=False))

    def test_original_timeout_strict_thresholds(self):
        now=[0];queue=Scheduler(clock=lambda:now[0])
        now[0]=10;self.assertIsNone(queue.connection_action())
        now[0]=11;self.assertEqual(queue.connection_action(),'reopen')
        now[0]=30;self.assertEqual(queue.connection_action(),'reopen')
        now[0]=31;self.assertEqual(queue.connection_action(),'reconnect')

    def test_all_three_startup_attempts_run(self):
        startup=StartupAttempts()
        for step in range(3):
            self.assertEqual(startup.begin(step*3).tag,1000)
            startup.mark_received()
            self.assertTrue(startup.should_advance(step*3))
            self.assertEqual(startup.finish_attempt(),step==2)


class SettingsRecoveryTests(unittest.TestCase):
    def test_key_sequences_and_original_level_gates(self):
        for level,word in enumerate(('user','regensvc','factory','programmer')):
            state=AccessKeySequence();result=None
            for char in word:result=state.feed(char,3146)
            self.assertEqual(result,level)
        self.assertTrue(access_allowed(1,0))
        self.assertFalse(access_allowed(2,0))
        self.assertTrue(access_allowed(2,6251))
        self.assertFalse(access_allowed(3,6251))

    def test_ini_case_insensitive_and_datalog_no_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.sp';config.write_text('[SPITFIRE]\nMaxLevel=6251\n')
            self.assertEqual(read_max_level(config),6251)
            log=Path(tmp)/'datalog.csv';append_datalog(1.234,5.678,log)
            # Text files use CRLF on Windows and LF on Linux; content is identical.
            self.assertEqual(log.read_text(encoding='ascii'),'1.23, 5.68\n')


if __name__=='__main__':unittest.main()
