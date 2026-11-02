import tempfile
from pathlib import Path
import unittest
from spitfire.scheduling import Scheduler, StartupAttempts
from spitfire.settings import AccessKeySequence, read_max_level, access_allowed, append_datalog


class SchedulingRecoveryTests(unittest.TestCase):
    def test_initial_priority_order_and_lbo_parameter(self):
        queue = Scheduler(); queue.queue_initial()
        messages = []
        while queue.inside:
            request = queue.next_request(auto_poll=False)
            messages.append(request)
            queue.acknowledge(request.tag)
        self.assertEqual(len(messages), 44)
        self.assertEqual([r.tag for r in messages[:9]], [1069, 2036, 1068, 1087, 1033, 1038, 1037, 1032, 1057])
        self.assertEqual([(r.tag, r.parameter) for r in messages[-3:]], [(2047, ' 1'), (1078, ''), (1062, '')])

    def test_priority_and_acknowledgement(self):
        queue = Scheduler();queue.push(1007, inside=False);queue.push(1038)
        self.assertEqual(queue.next_request().tag, 1038)
        self.assertIsNone(queue.next_request())
        queue.acknowledge(1038)
        self.assertEqual(queue.next_request().tag, 1007)

    def test_user_and_service_poll_cycles(self):
        queue=Scheduler();queue.queue_poll()
        self.assertEqual(len(queue.outside),29)
        self.assertEqual([r.tag for r in queue.outside][:5],[1039,1015,1039,1019,1039])
        queue.clear();queue.access_level=1;queue.queue_poll()
        self.assertEqual(len(queue.outside),37)
        self.assertEqual([r.tag for r in queue.outside][:9],[1039,1056,1039,1055,1039,1042,1039,1043,1039])

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
            self.assertEqual(log.read_bytes(),b'1.23, 5.68\n')


if __name__=='__main__':unittest.main()
