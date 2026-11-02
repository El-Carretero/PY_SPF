import unittest
from unittest.mock import patch
from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.callbacks import Action


class ControllerRecoveryTests(unittest.TestCase):
    def make_controller(self, demo=True):
        now=[0.0];view=MemoryView()
        controller=Controller(view,demo=demo,tcp_port=None,clock=lambda:now[0])
        return controller,view,now

    def test_simulator_initializes_without_changing_readback_preference(self):
        controller,view,now=self.make_controller()
        view.values[6,48]=0
        controller.start()
        try:
            for _ in range(130):controller.tick()
            self.assertTrue(controller.state['connected'])
            self.assertEqual(view.values[6,48],0)
            self.assertFalse(controller.scheduler.hold)
            self.assertFalse(any(kind=='callback' for _,kind,_ in controller.events))
        finally:controller.stop()

    def test_startup_advances_only_after_original_identity_response(self):
        controller,view,now=self.make_controller()
        controller.start()
        try:
            controller._receive('(1,1)<1013>0')
            self.assertFalse(controller.startup.received)
            controller._receive('(1,2)<1000>identity')
            self.assertTrue(controller.startup.received)
            self.assertNotIn('pardon_first_time_user',controller.state)
        finally:controller.stop()

    def test_hold_requires_more_than_three_whole_seconds(self):
        controller,view,now=self.make_controller()
        controller.handle_callback('cllbck',event=3,panel=2,control=8)
        self.assertEqual(controller.state['evnt_cmt'],1)
        controller._held_turn_on(3.99)
        self.assertFalse(controller.scheduler.inside)
        controller._held_turn_on(4.0)
        self.assertEqual([(r.tag,r.parameter) for r in controller.scheduler.inside],[(2027,'')])
        self.assertEqual(view.values[2,8],1)
        self.assertEqual(controller.state['evnt_cmt'],0)
        controller._held_turn_on(8)
        self.assertEqual(len(controller.scheduler.inside),1)

    def test_release_cancels_hold_and_idle_release_does_not_send_motor_stop(self):
        controller,view,now=self.make_controller()
        controller.handle_callback('cllbck',event=3,panel=2,control=8)
        controller.handle_callback('cllbck',event=1,panel=2,control=8)
        controller.tick()
        controller.mouse_released()
        self.assertFalse(controller.scheduler.inside)
        self.assertIsNone(controller._button_started)

    def test_udp_open_retries_for_three_seconds_without_modal(self):
        controller,view,now=self.make_controller(demo=False)
        with patch('spitfire.controller.UDPTransport') as transport:
            transport.return_value.open.side_effect=OSError('bind failed')
            controller.connect()
            self.assertEqual(transport.return_value.open.call_count,1)
            now[0]=2;controller.tick()
            self.assertEqual(transport.return_value.open.call_count,2)
            now[0]=3;controller.tick()
            self.assertTrue(controller.scheduler.hold)
            self.assertEqual(view.values[6,54],'Com error - cannot open!')
            self.assertIsNone(controller._opening_deadline)

    def test_silent_board_reports_connection_failure_without_claiming_ready(self):
        from spitfire.simulator import SimulatedTransport

        class SilentBoard(SimulatedTransport):
            def receive(self):
                return []

        controller,view,now=self.make_controller()
        with patch('spitfire.controller.SimulatedTransport', SilentBoard):
            controller.start()
            try:
                for deadline in (3,6,9):
                    now[0]=deadline
                    controller.tick()
                self.assertIn('No reply from 10.19.70.13:1024',view.read(6,54))
                self.assertIn('run_demo.bat',view.read(6,54))
                self.assertFalse(controller.state['connected'])
                self.assertEqual(controller.state['curtain_not_open'],1)
                self.assertEqual(controller.attributes[6,49,530],1)
                self.assertEqual(view.menu_attributes[6,0,500],1)
                self.assertFalse(any('[2036]' in payload for _,kind,payload in controller.events if kind=='TX'))
            finally:controller.stop()

    def test_action_adapters_keypress_and_server_text(self):
        controller,view,now=self.make_controller()
        class Server:
            def __init__(self):self.messages=[]
            def send_text(self,value):self.messages.append(value+'\n')
        controller.tcp=Server()
        controller.apply([Action('server_write',None,'hello\n'),Action('reset_textbox',('server',4),'')])
        self.assertEqual(controller.tcp.messages,['hello\n'])
        self.assertEqual(view.values['server',4],'')
        controller.apply([Action('key_pressed',None,c) for c in 'regensvc'])
        self.assertEqual(controller.scheduler.access_level,1)


if __name__=='__main__':unittest.main()
