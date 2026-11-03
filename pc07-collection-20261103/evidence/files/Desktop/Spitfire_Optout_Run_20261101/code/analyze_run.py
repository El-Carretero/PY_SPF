#!/usr/bin/env python3
"""Summarize observed original-XP UDP and action evidence; stdlib only.
No network/UI operations. Raw logs are never modified. Derived outputs may be replaced.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics

REQUEST_PREFIX = b'Spectra-Physics:CMD_ECLIPSE,'
REPLY_PREFIX = b'Spectra-Physics:REPLY_ECLIPSE:'
ORIGINAL_PATH = r'C:\Program Files\Spectra-Physics\Spitfire\Spitfire.exe'
EXPECTED = {'about':'Help','temperature':'Temperature Control','timing':'Timing and High Voltage',
            'faults':'Active Faults','setup':'Empower Setup','regensvc':'Empower Service'}
KST = timezone(timedelta(hours=9))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_lines(path, warnings):
    if not path.exists():
        return []
    result = []
    for number, line in enumerate(path.read_text(encoding='utf-8-sig', errors='replace').splitlines(), 1):
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except ValueError as exc:
            warnings.append('%s:%d not valid JSON: %s' % (path.name, number, exc))
    return result


def epoch(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def iso(value, zone=timezone.utc):
    if value is None:
        return ''
    return datetime.fromtimestamp(value, zone).isoformat()


def wire_messages(record, field, prefix, pattern, warnings):
    raw_hex = record.get(field)
    if raw_hex is None:
        return []
    try:
        raw = bytes.fromhex(raw_hex)
    except (ValueError, TypeError):
        warnings.append('Invalid %s at UDP seq %s' % (field, record.get('seq')))
        return []
    if not raw.startswith(prefix):
        warnings.append('Unexpected %s envelope at UDP seq %s' % (field, record.get('seq')))
        return []
    result = []
    for line in raw[len(prefix):].splitlines():
        m = re.fullmatch(pattern, line)
        if m:
            result.append((int(m[1]), m[2].decode('ascii', errors='replace')))
        else:
            warnings.append('Malformed %s line at UDP seq %s' % (field, record.get('seq')))
    return result


def duration_stats(times):
    times = sorted(times)
    deltas = [b-a for a,b in zip(times, times[1:])]
    return {'count':len(times), 'first_utc':iso(times[0]) if times else None,
            'last_utc':iso(times[-1]) if times else None, 'interval_count':len(deltas),
            'interval_min_s':min(deltas) if deltas else None,
            'interval_median_s':statistics.median(deltas) if deltas else None,
            'interval_mean_s':statistics.mean(deltas) if deltas else None,
            'interval_max_s':max(deltas) if deltas else None}


def correlate_action_clocks(actions, issued_actions, host_events, warnings):
    """Use causal host bounds, never guest wall time, to align action evidence."""
    intervals = {}
    def item(seq, mode):
        return intervals.setdefault((str(seq), mode), {
            'seq':str(seq), 'action':mode, 'host_issue_utc':None,
            'host_first_artifact_upload_utc':None, 'host_last_artifact_upload_utc':None,
            'host_completion_upload_utc':None, 'host_interval_duration_s':None,
            'host_interval_complete':False, 'guest_start_utc':None, 'guest_end_utc':None})
    for act in actions:
        item(act['seq'], act['mode']).update(guest_start_utc=act['guest_start_utc'],
                                            guest_end_utc=act['guest_end_utc'])
    for act in issued_actions:
        entry = item(act['seq'], act['action'])
        if entry['host_issue_utc'] is not None:
            warnings.append('Repeated action issue for %s-%s; retaining earliest host time' %
                            (act['seq'], act['action']))
        old = epoch(entry['host_issue_utc'])
        if act['epoch'] is not None and (old is None or act['epoch'] < old):
            entry['host_issue_utc'] = iso(act['epoch'])
    for event in host_events:
        if event.get('kind') != 'upload':
            continue
        name = event.get('file', '')
        match = re.fullmatch(r'(\d+)-([a-z_]+)-(.*)', name)
        if not match:
            continue
        seq, mode, leaf = match.groups()
        t = epoch(event.get('utc'))
        if t is None:
            continue
        entry = item(seq, mode)
        first = epoch(entry['host_first_artifact_upload_utc'])
        last = epoch(entry['host_last_artifact_upload_utc'])
        if first is None or t < first:
            entry['host_first_artifact_upload_utc'] = iso(t)
        if last is None or t > last:
            entry['host_last_artifact_upload_utc'] = iso(t)
        if leaf == 'complete.txt':
            entry['host_completion_upload_utc'] = iso(t)
    skew_samples = []
    for entry in intervals.values():
        start = epoch(entry['host_issue_utc'])
        end = epoch(entry['host_completion_upload_utc'])
        if start is not None and end is not None:
            entry['host_interval_complete'] = end >= start
            entry['host_interval_duration_s'] = end - start
            if end < start:
                warnings.append('Host completion precedes issue for %s-%s' %
                                (entry['seq'], entry['action']))
        guest_start = epoch(entry['guest_start_utc'])
        guest_end = epoch(entry['guest_end_utc'])
        first_upload = epoch(entry['host_first_artifact_upload_utc'])
        # The synchronous driver returns before the HTA uploads any artifact.
        # Thus issue <= corrected guest begin, corrected guest end <= first upload.
        lower = start - guest_start if start is not None and guest_start is not None else None
        upper = first_upload - guest_end if first_upload is not None and guest_end is not None else None
        if lower is not None or upper is not None:
            consistent = lower is None or upper is None or lower <= upper
            sample = {'seq':entry['seq'], 'action':entry['action'],
                      'host_minus_guest_lower_bound_s':lower,
                      'host_minus_guest_upper_bound_s':upper,
                      'bounds_consistent':consistent,
                      'midpoint_estimate_s':(lower+upper)/2 if consistent and lower is not None and upper is not None else None}
            skew_samples.append(sample)
            if not consistent:
                warnings.append('Inconsistent clock bounds for %s-%s; possible clock jump or mismatched evidence' %
                                (entry['seq'], entry['action']))
    valid = [x for x in skew_samples if x['bounds_consistent']]
    lower = max((x['host_minus_guest_lower_bound_s'] for x in valid
                 if x['host_minus_guest_lower_bound_s'] is not None), default=None)
    upper = min((x['host_minus_guest_upper_bound_s'] for x in valid
                 if x['host_minus_guest_upper_bound_s'] is not None), default=None)
    overlap = lower is not None and upper is not None and lower <= upper
    skew = {'definition':'positive host_minus_guest means the XP clock is behind the host clock',
            'method':'host action issue <= guest begin plus offset; guest end plus offset <= first artifact upload; assumes stable clocks within each action',
            'samples':skew_samples,
            'constant_offset_compatible':overlap if lower is not None and upper is not None else None,
            'constant_offset_lower_bound_s':lower if overlap else None,
            'constant_offset_upper_bound_s':upper if overlap else None,
            'approximate_host_minus_guest_s':(lower+upper)/2 if overlap else None,
            'uncertainty_note':'Causal bounds include polling, action and upload delays. The midpoint is an estimate, not a clock synchronization measurement. No timestamps are corrected.',
            'guest_clock_modified':False}
    rows = sorted(intervals.values(), key=lambda x:(int(x['seq']) if x['seq'].isdigit() else -1,x['action']))
    by_key = {(x['seq'],x['action']):x for x in rows}
    for act in actions:
        act['host_action_interval'] = by_key[(act['seq'],act['mode'])]
    return rows, skew


def run(root, out):
    warnings = []
    udp_path = root/'udp-original.jsonl'
    if not udp_path.is_file():
        raise ValueError('Missing actual udp-original.jsonl; no results invented')
    records = read_lines(udp_path, warnings)
    received = root/'received'
    screenshot_exports = {}
    screenshot_index = root/'screenshot-index.csv'
    if screenshot_index.exists():
        with screenshot_index.open(encoding='utf-8-sig', newline='') as f:
            screenshot_exports = {x['raw_bmp']: x['png'] for x in csv.DictReader(f)}
    actions = []
    timeline_rows = []
    launches = []
    all_helpers_no_udp = True
    for result_path in sorted(received.glob('*-result.json')):
        m = re.fullmatch(r'(\d+)-([a-z_]+)-result\.json', result_path.name)
        if not m:
            continue
        seq, mode = m[1], m[2]
        prefix = '%s-%s-' % (seq, mode)
        value = read_json(result_path)
        path = received/(prefix+'timeline.jsonl')
        events = read_lines(path, warnings)
        windows = read_lines(received/(prefix+'windows.jsonl'), warnings)
        pid = value.get('original_pid')
        visible = sorted({x.get('text','') for x in windows if x.get('kind')=='window' and
                          x.get('visible') and x.get('pid')==pid and x.get('text')})
        before = received/(prefix+'desktop-before.bmp')
        after = received/(prefix+'desktop.bmp')
        action = {'seq':seq,'mode':mode,'result':value,'visible_original_windows_after':visible,
                  'expected_window':EXPECTED.get(mode),'expected_window_observed':
                  EXPECTED[mode] in visible if mode in EXPECTED else None,
                  'before_screenshot':before.name if before.exists() or before.name in screenshot_exports else None,
                  'before_exported_screenshot':screenshot_exports.get(before.name),
                  'after_screenshot':after.name if after.exists() or after.name in screenshot_exports else None,
                  'after_exported_screenshot':screenshot_exports.get(after.name),
                  'result_file':result_path.name,'result_sha256':sha(result_path)}
        action['guest_event_evidence'] = [{k:e.get(k) for k in ('utc_guest_clock','action','phase','detail','code')}
                                          for e in events]
        times = [epoch(e.get('utc_guest_clock')) for e in events]
        times = [x for x in times if x is not None]
        action['guest_start_utc'] = iso(min(times)) if times else None
        action['guest_end_utc'] = iso(max(times)) if times else None
        if value.get('helper_udp_generated') is not False:
            all_helpers_no_udp = False
        actions.append(action)
        launch_path = received/(prefix+'launched-original.json')
        if launch_path.exists():
            launch = read_json(launch_path)
            launches.append({'seq':seq,'mode':mode,'artifact':launch_path.name,**launch})
        for e in events:
            t = epoch(e.get('utc_guest_clock'))
            timeline_rows.append({'utc':iso(t),'kst':iso(t,KST),'clock':'guest','seq':seq,'action':mode,
                                  'phase':e.get('phase',''),'event':e.get('action',''),
                                  'detail':e.get('detail',''),'code':e.get('code','')})
    issued = read_lines(root/'actions-issued.jsonl', warnings)
    issued_actions = []
    for e in issued:
        t = next((epoch(e.get(k)) for k in ('utc','issued_utc','epoch','time') if epoch(e.get(k)) is not None),None)
        mode = e.get('action', e.get('mode',e.get('verb','')))
        seq = str(e.get('seq',e.get('sequence','')))
        for field in ('command','control','text'):
            candidate=e.get(field)
            if isinstance(candidate,str) and re.fullmatch(r'\d+\|[a-z_]+',candidate):
                seq,mode=candidate.split('|',1)
                break
        issued_actions.append({'seq':seq,'action':mode,'epoch':t,'raw':e})
        timeline_rows.append({'utc':iso(t),'kst':iso(t,KST),'clock':'host','seq':seq,'action':mode,
                              'phase':'issued','event':'action_issue','detail':json.dumps(e,ensure_ascii=False),'code':''})
    host_events = read_lines(root/'host-timeline.jsonl', warnings)
    for e in host_events:
        t=epoch(e.get('utc'))
        match=re.fullmatch(r'(\d+)-([a-z_]+)-(.*)',e.get('file',''))
        timeline_rows.append({'utc':iso(t),'kst':iso(t,KST),'clock':'host',
                              'seq':match[1] if match else '', 'action':match[2] if match else '',
                              'phase':e.get('kind',''),'event':'host_event','detail':
                              e.get('file',json.dumps({k:v for k,v in e.items() if k!='utc'},ensure_ascii=False)), 'code':''})
    action_intervals, clock_skew = correlate_action_clocks(actions, issued_actions, host_events, warnings)
    interval_by_key = {(x['seq'],x['action']):x for x in action_intervals}
    for row in timeline_rows:
        interval = interval_by_key.get((row['seq'],row['action']),{})
        row['host_action_issue_utc'] = interval.get('host_issue_utc')
        row['host_action_completion_upload_utc'] = interval.get('host_completion_upload_utc')

    requests=[];responses=[];cmd_events=[];transitions=[];readbacks=[];latencies=[]
    accepted_records=[]
    for rec in records:
        source=rec.get('source',[])
        if source!=['10.19.70.2',1024]:
            warnings.append('UDP seq %s not from expected guest endpoint; excluded from original request counts'%rec.get('seq'))
            continue
        rt=epoch(rec.get('received_epoch'));st=epoch(rec.get('sent_epoch'))
        if rt is None:
            warnings.append('UDP seq %s missing receive timestamp'%rec.get('seq'));continue
        req=wire_messages(rec,'request_hex',REQUEST_PREFIX,rb'\[(\d+)\](.*)',warnings)
        rep=wire_messages(rec,'reply_hex',REPLY_PREFIX,rb'<(\d+)>(.*)',warnings)
        if req:accepted_records.append(rec)
        events=list(rec.get('messages',[]))
        for i,(tag,body) in enumerate(req):
            ev=next((e for e in events if e.get('tag')==tag and e.get('command')==body),{})
            if ev:events.remove(ev)
            entry={'udp_seq':rec.get('seq'),'timestamp':rt,'tag':tag,'command':body,'event':ev}
            requests.append(entry)
            if tag>=2000:
                cmd_events.append({'utc':iso(rt),'udp_seq':rec.get('seq'),'tag':tag,'wire_command':body,
                                   'simulator_action':ev.get('action'),
                                   'before':ev.get('before'),'after':ev.get('after')})
            if tag==2036 and ev.get('before')=='0' and ev.get('after')=='1':
                transitions.append({'timestamp':rt,'utc':iso(rt),'udp_seq':rec.get('seq'),
                                    'wire_command':body,'synthetic_state_change':'0 -> 1 in simulator RAM'})
        for tag,body in rep:
            responses.append({'udp_seq':rec.get('seq'),'timestamp':st,'tag':tag,'value':body})
            if tag==1068:readbacks.append({'timestamp':st,'utc':iso(st),'udp_seq':rec.get('seq'),'value':body})
        if req and rep and st is not None:latencies.append(st-rt)

    for interval in action_intervals:
        begin=epoch(interval['host_issue_utc']);end=epoch(interval['host_completion_upload_utc'])
        contained=[x for x in requests if begin<=x['timestamp']<=end] if interval['host_interval_complete'] else []
        interval['request_messages_within_host_interval']=len(contained) if interval['host_interval_complete'] else None
        interval['request_tag_counts_within_host_interval']=dict(Counter(str(x['tag']) for x in contained)) if interval['host_interval_complete'] else None
        interval['first_request_within_host_interval_utc']=iso(min((x['timestamp'] for x in contained),default=None))
        interval['last_request_within_host_interval_utc']=iso(max((x['timestamp'] for x in contained),default=None))

    transition=transitions[0]['timestamp'] if transitions else None
    optout_ui_actions=[]
    for act in actions:
        if act['mode']!='optout_on':continue
        interval=act['host_action_interval'];issue=epoch(interval['host_issue_utc'])
        phases=[e.get('phase') for e in act['guest_event_evidence'] if e.get('action')=='optout_on']
        optout_ui_actions.append({'seq':act['seq'],'exit_code':act['result'].get('exit_code'),
                                  'guest_event_phases':phases,
                                  'already_on_no_input_reported':'already_on' in phases,
                                  'host_issue_utc':interval['host_issue_utc'],
                                  'host_completion_upload_utc':interval['host_completion_upload_utc'],
                                  'first_simulator_transition_precedes_issue':transition<issue
                                      if transition is not None and issue is not None else None})
    attribution_path=root/'user-input-attribution.json'
    user_attribution=read_json(attribution_path) if attribution_path.exists() else None
    for event in cmd_events:
        t=epoch(event['utc'])
        event['enclosing_host_action_intervals']=[{'seq':x['seq'],'action':x['action']}
            for x in action_intervals if x['host_interval_complete'] and
            epoch(x['host_issue_utc'])<=t<=epoch(x['host_completion_upload_utc'])]
    successful_launch_seqs={str(x['seq']) for x in launches if x.get('path','').lower()==ORIGINAL_PATH.lower()}
    restart_candidates=[x for x in issued_actions if x['action']=='launch' and x['seq'] in successful_launch_seqs and
                        x['epoch'] is not None and transition is not None and x['epoch']>transition]
    restart=min((x['epoch'] for x in restart_candidates),default=None)
    restart_definition='host issue time for a post-transition launch independently matched to launch artifact'
    identity_after=[x['timestamp'] for x in requests if x['tag']==1000 and transition is not None and x['timestamp']>transition]
    if restart is None and identity_after:
        restart=min(identity_after)
        restart_definition='first post-transition1000 identity request; handshake evidence only, process restart timing not established'
    def phase(t):
        if transition is None:return 'no_observed_optout_transition'
        if t<transition:return 'before_optout_on'
        if restart is not None and t>=restart:return 'after_restart_issue_or_handshake'
        return 'after_optout_on_before_restart'
    buckets=defaultdict(list)
    for x in requests:
        if x['tag']<2000:buckets[(phase(x['timestamp']),x['tag'],x['command'])].append(x['timestamp'])
    qrows=[]
    for (stage,tag,command),times in sorted(buckets.items()):
        qrows.append({'phase':stage,'tag':tag,'command':command,**duration_stats(times)})
    count_requests=Counter(str(x['tag']) for x in requests)
    count_responses=Counter(str(x['tag']) for x in responses)
    orig_exe=received/'original-SPITFIRE.EXE'
    matched=bool(successful_launch_seqs and actions and all_helpers_no_udp and orig_exe.is_file() and
                 any(x['result'].get('original_exact_count')==1 and not x['result'].get('foreign_original_name') for x in actions))
    identity_requests=[{'utc':iso(x['timestamp']),'udp_seq':x['udp_seq'],'command':x['command'],
                        'phase':phase(x['timestamp'])} for x in requests if x['tag']==1000]
    action_modes=defaultdict(lambda:{'observed_results':0,'exit_zero':0,'nonzero':0})
    for act in actions:
        m=action_modes[act['mode']];m['observed_results']+=1
        m['exit_zero' if act['result'].get('exit_code')==0 else 'nonzero']+=1
    summary={'source_udp_log':str(udp_path),'source_udp_sha256':sha(udp_path),
             'request_provenance':'original XP application matched to launch/process/no-helper-UDP evidence' if matched else
                 'guest endpoint traffic; original process attribution incomplete',
             'attribution_limit':'Packet log itself has no Windows PID; identity is cross-checked against independent launch/process artifacts.',
             'responses_provenance':'synthetic simulator; not physical controller behavior',
             'physical_controller_tested':False,'original_executable_sha256':sha(orig_exe) if orig_exe.exists() else None,
             'original_launch_artifacts':launches,'all_action_results_assert_no_helper_udp':all_helpers_no_udp if actions else None,
             'udp_records_total':len(records),'accepted_request_datagrams':len(accepted_records),
             'reply_datagrams':sum('reply_hex' in r for r in accepted_records),
             'request_messages':len(requests),'response_messages':len(responses),
             'request_tag_counts':dict(sorted(count_requests.items(),key=lambda x:int(x[0]))),
             'response_tag_counts':dict(sorted(count_responses.items(),key=lambda x:int(x[0]))),
             'first_request_utc':iso(min((x['timestamp'] for x in requests),default=None)),
             'last_request_utc':iso(max((x['timestamp'] for x in requests),default=None)),
             'optout_transitions':transitions,'optout_readbacks':readbacks,'command_events':cmd_events,
             'optout_ui_automation_evidence':optout_ui_actions,
             'user_input_attribution':user_attribution,
             'user_input_attribution_sha256':sha(attribution_path) if attribution_path.exists() else None,
             'optout_causality_note':'Wire evidence identifies original requests and synthetic state changes. Enclosing action intervals are timing context, not proof of input causation. User statements are separately sourced. An already_on automation result sends no click and does not validate the automation OFF-to-ON path.',
             'identity_requests':identity_requests,'phase_boundaries':{'first_optout_transition_utc':iso(transition),
                 'restart_utc':iso(restart),'restart_definition':restart_definition if restart is not None else None},
             'interarrival_stats_note':'Intervals use host receive timestamps, include initialization/navigation/gaps, and are observed request intervals, not a fixed hardware polling period.',
             'simulator_processing_latency_s':{'count':len(latencies),'min':min(latencies) if latencies else None,
                 'median':statistics.median(latencies) if latencies else None,'max':max(latencies) if latencies else None},
             'latency_note':'host Python receive-to-send timing; not NIC RTT; use pcap for network timing',
             'action_coverage':dict(action_modes),'actions':actions,'host_action_intervals':action_intervals,
             'action_packet_alignment_note':'Packet counts use only the enclosing host issue-to-completion-upload interval. They include background polls and upload delays; they do not prove an exact UI click timestamp or causal command attribution.',
             'query_summary_rows':len(qrows),'warnings':warnings,'guest_host_clock_skew':clock_skew,
             'clock_note':'Guest and host UTC clocks are kept distinct. Guest event timestamps are never compared directly to packet timestamps. Timeline CSV groups rows by clock instead of interleaving incompatible clocks; no clock offset correction has been applied.',
             'no_unseen_actions_inferred':True}
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with (out/'query-summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['phase','tag','command','count','first_utc','last_utc','interval_count','interval_min_s','interval_median_s','interval_mean_s','interval_max_s']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(qrows)
    with (out/'action-timeline.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['utc','kst','clock','seq','action','phase','event','detail','code',
                                           'host_action_issue_utc','host_action_completion_upload_utc'])
        writer.writeheader();writer.writerows(sorted(timeline_rows,key=lambda x:(x['clock'],x['utc'],x['seq'])))
    with (out/'action-intervals.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['seq','action','host_issue_utc','host_first_artifact_upload_utc','host_last_artifact_upload_utc',
                'host_completion_upload_utc','host_interval_duration_s','host_interval_complete',
                'guest_start_utc','guest_end_utc','request_messages_within_host_interval',
                'request_tag_counts_within_host_interval','first_request_within_host_interval_utc',
                'last_request_within_host_interval_utc']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({**x,'request_tag_counts_within_host_interval':json.dumps(x['request_tag_counts_within_host_interval'])}
                         for x in action_intervals)
    print(json.dumps({'request_datagrams':len(accepted_records),'reply_datagrams':summary['reply_datagrams'],
                      'optout_transition_count':len(transitions),'readback_values':[x['value'] for x in readbacks],
                      'action_modes':dict(action_modes),'warnings':len(warnings),'summary':str(out/'summary.json')},indent=2))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args();run(a.root,a.out or a.root/'analysis')

if __name__=='__main__':main()
