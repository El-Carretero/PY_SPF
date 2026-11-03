/* Node-only mocked orchestration tests. Does not touch any Windows machine. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '..', 'runner.js'), 'utf8');
const fixtureDir = path.join(__dirname, 'fixtures', 'report-field');
function fieldFixture(name) { return JSON.parse(fs.readFileSync(path.join(fixtureDir, name), 'utf8').replace(/^\uFEFF/, '')); }

function rig(options) {
  const o = Object.assign({ probeExit: 0, installExit: 0, preflightExit: 0,
    optout: 1, access: 0, ready: true, captureExit: 0 }, options || {});
  let time = Date.UTC(2026, 10, 1), tickTime = 10000;
  let access = o.access, capture = null, currentChild = null, actionsStarted = 0;
  let statusReadFailures = 0, statusReadAllFailures = 0, statusCloses = 0, statusPrivateReads = 0;
  let publishExits = (o.publishExits || []).slice(), snapshotExits = (o.snapshotExits || []).slice();
  const files = {}, runs = [], ui = {}, processes = [], base = 'C:\\SpitfireLogs\\test';
  function fakeDate() { return new Date(time); }
  fakeDate.prototype = Date.prototype;
  const fileSystem = {
    CreateFolder() {}, FolderExists() { return true; },
    GetParentFolderName(p) { return p.slice(0, p.lastIndexOf('\\')); },
    FileExists(p) { return Object.prototype.hasOwnProperty.call(files, p); },
    CreateTextFile(p) { files[p] = ''; return { Write(s) { files[p] += s; }, WriteLine(s) { files[p] += s+'\r\n'; }, Close() {} }; },
    OpenTextFile(p, mode, create) {
      if (mode === 1 && /\\capture-status\.json$/.test(p) && statusReadFailures > 0) {
        statusReadFailures--; throw new Error('Mock transient sharing violation');
      }
      if (!Object.prototype.hasOwnProperty.call(files, p)) {
        if (!create) throw new Error('File missing: ' + p);
        files[p] = '';
      }
      return { ReadAll() { if (/\\capture-status\.json$/.test(p)) { statusPrivateReads++; if (statusReadAllFailures > 0) {statusReadAllFailures--; throw new Error('Mock ReadAll failure');} } return files[p]; }, WriteLine(s) { files[p] += s+'\r\n'; }, Close() { if (/\\capture-status\.json$/.test(p)) statusCloses++; } };
    },
    DeleteFile(p) { delete files[p]; },
    MoveFile(a, b) { files[b] = files[a]; delete files[a]; }
  };
  function put(p, value) { files[p] = JSON.stringify(value); }
  if (o.preflightWindows) files[base + '\\actions\\00-preflight\\windows-before.jsonl'] = o.preflightWindows;
  function status(final) {
    const count = o.ready ? Math.max(3, Math.floor((tickTime - 10000) / 10)) : 0;
    const writes = o.writeAfterAction && actionsStarted >= o.writeAfterAction ? 1 : 0;
    return { schema: 1, updated_tick: tickTime, tick_ms: tickTime,
      stage: final ? 'complete' : 'capturing', ui_ready: o.ready && !writes,
      capture_ready: true, observed_pairs: o.ready ? 1 : 0, candidate_pairs: o.ready ? 1 : 0,
      command_packets: count, response_packets: count, any_write_commands: writes,
      first_write_command: writes ? '[2047]EMP:LBOBREAK 1' : '',
      adapter_errors: 0, io_errors: 0, status_write_errors: 0, capture_drops: 0,
      malformed_commands: 0, blocked_reason: '', active_adapters: 1,
      pcap_validation_ok: o.pcapValidation !== false, capture_stats_unavailable: 0,
      enumeration_overflow: 0, truncated_frames: 0,
      adapters: [{ id: 1, frames: count * 2, command_frames: count, response_frames: count,
        opened: true, finished: !!final, stats_valid: true, ps_drop: 0, ps_ifdrop: 0 }],
      pairs: [{ commands: count, responses: count, interface_id: 1 }], tags: [] };
  }
  const shell = {
    Run(s, style, wait) {
      runs.push(s);
      if (s.indexOf('proof_publish.exe') >= 0 && s.indexOf(' --snapshot ') >= 0) {
        assert.equal(style, 0, 'snapshot reader must stay hidden'); assert.equal(wait, true, 'snapshot must complete before FSO reads it');
        const match = /proof_publish\.exe" --snapshot "([^"]+)" "([^"]+)"/.exec(s); assert(match, s);
        assert.equal(match[1], base+'\\capture\\status.json'); assert.equal(match[2], base+'\\capture-status.json');
        const code = snapshotExits.length ? snapshotExits.shift() : (o.snapshotExit || 0);
        if (code === 0) { assert(Object.prototype.hasOwnProperty.call(files, match[1])); files[match[2]] = files[match[1]]; }
        return code;
      }
      if (s.indexOf('proof_publish.exe') >= 0) {
        assert.equal(style, 0, 'publisher must stay hidden'); assert.equal(wait, true, 'publication must complete before use');
        const match = /proof_publish\.exe" "([^"]+)" "([^"]+)"/.exec(s); assert(match, s);
        const code = publishExits.length ? publishExits.shift() : (o.publishExit || 0);
        if (code === 0) { assert(Object.prototype.hasOwnProperty.call(files, match[1])); files[match[2]] = files[match[1]]; delete files[match[1]]; }
        return code;
      }
      return 0;
    },
    Exec(command) {
      runs.push(command);
      const p = { Status: 0, ExitCode: 0, ProcessID: 1000 + processes.length,
        Terminate() { this.Status = 1; this.ExitCode = 99; this.terminated = true; },
        completeAt: time + 600, command };
      processes.push(p);
      if (command.indexOf('passive_capture.exe') >= 0 && command.indexOf('--probe') < 0) {
        capture = p; p.completeAt = Infinity;
        put(base + '\\capture\\status.json', status(false));
      } else if (command.indexOf('--probe') >= 0) {
        p.ExitCode = command.indexOf('driver-after') >= 0 ? 0 : o.probeExit;
      } else if (command.indexOf('provision_winpcap.exe') >= 0) {
        p.ExitCode = o.installExit;
      } else if (command.indexOf('readonly_ui.exe') >= 0) {
        const match = /readonly_ui\.exe" ([a-z]+) "([^"]+)"/.exec(command);
        assert(match, command);
        p.mode = match[1]; p.out = match[2];
        if (p.mode === 'preflight') p.ExitCode = o.preflightExit;
        else {
          actionsStarted++;
          if (o.actionDuration) p.completeAt = time + o.actionDuration;
          if (o.actionExit && actionsStarted === (o.failAction || 1)) p.ExitCode = o.actionExit;
        }
      } else throw new Error('Unexpected process: ' + command);
      currentChild = p;
      return p;
    }
  };
  const context = { Date: fakeDate, Math, isFinite, decodeURIComponent,
    location: { pathname: '/C:/SpitfireLogs/test/app/RUN.hta' },
    window: { resizeTo() {}, setInterval() { return 1; }, clearInterval() {} },
    document: { getElementById(id) { return ui[id] || (ui[id] = {}); } },
    ActiveXObject: function(name) { if (name === 'Scripting.FileSystemObject') return fileSystem; if (name === 'WScript.Shell') return shell; throw new Error(name); }
  };
  vm.createContext(context); vm.runInContext(source, context);
  /* Rendering is tested separately; these tests exercise state/stop semantics. */
  context.makeReport = function(result) { if (o.reportFailure) throw new Error('Mock report output failure'); };
  function step() {
    time += 300; tickTime += 300;
    for (const p of processes) if (p.Status === 0 && time >= p.completeAt) {
      p.Status = 1;
      if (p.mode) {
        if (p.mode !== 'preflight' && o.changedAccess) access = o.access === 0 ? 1 : 0;
        if (p.mode === 'preflight' || !o.missingActionResult) {
          let result = { mode: p.mode, original_pid: p.mode !== 'preflight' && o.changedPid ? 4321 : 1234, preflight_ready: o.preflightExit === 0,
            emp_optout: p.mode !== 'preflight' && o.actionOptoutOff ? 0 : o.optout, gAccessLevel: access, exit_code: p.ExitCode, original_left_running: true,
            skipped: p.mode === 'setup' && access === 0 && o.optout === 1,
            skip_reason: p.mode === 'setup' && access === 0 && o.optout === 1 ? 'User-mode Opt-out setup display is intentionally skipped before input' : '' };
          if (p.mode === 'preflight' && o.preflightResult) result = o.preflightResult;
          if (p.mode !== 'preflight' && o.actionResult) result = o.actionResult;
          if (p.mode !== 'preflight' && o.actionEvidenceOverrides) result = Object.assign({}, result, o.actionEvidenceOverrides);
          if (p.mode !== 'preflight' && o.actionRaw) files[p.out + '\\result.json'] = o.actionRaw;
          else put(p.out + '\\result.json', result);
        }
      }
    }
    if (capture && capture.Status === 0) {
      put(base + '\\capture\\status.json', status(false));
      if (files[base + '\\STOP'] || (o.captureEarly && actionsStarted >= o.captureEarly)) {
        capture.Status = 1; capture.ExitCode = o.captureExit;
        if (!o.noSummary) {
          const s = status(true);
          if (o.summaryIOError) s.io_errors = 1;
          if (o.summaryNoReply) s.response_packets = 0;
          put(base + '\\capture\\summary.json', s);
        }
      }
    }
    context.tick();
  }
  function run() { context.begin(); for (let i = 0; i < 2000 && !context.finished; i++) step(); assert(context.finished, 'runner did not finish'); return JSON.parse(files[base + '\\result.json']); }
  return { context, files, runs, processes, base, step, run, ui,
    setStatusReadFailures(n) { statusReadFailures = n; },
    setPublishExits(codes) { publishExits = codes.slice(); },
    setSnapshotExits(codes) { snapshotExits = codes.slice(); },
    setStatusReadAllFailures(n) { statusReadAllFailures = n; },
    get statusCloses() { return statusCloses; },
    get statusPrivateReads() { return statusPrivateReads; },
    get access() { return access; } };
}

const tests = [];
function test(name, f) { tests.push([name, f]); }
function uiActions(r) { return r.runs.filter(s => /readonly_ui\.exe" (?!preflight)/.test(s)); }
function reach(r, stage) { r.context.begin(); for (let i = 0; i < 500 && r.context.stage !== stage; i++) r.step(); assert.equal(r.context.stage, stage); }
test('successful normal-user pass keeps the original mode and checks five fixed screens', () => {
  const r = rig(); const v = r.run(); assert.equal(v.outcome, 'COMPLETED'); assert.equal(uiActions(r).length, 5); assert.equal(r.access, 0);
  assert(Array.isArray(v.actions)); assert.equal(v.actions.length, 5);
  assert.deepEqual(v.actions.map(a => a.mode), ['temperature', 'timing', 'faults', 'setup', 'about']);
  assert.equal(v.actions.filter(a => a.result.skipped).length, 1);
  assert.equal(v.actions[3].result.skipped, true);
  assert.equal(v.actions.filter(a => !a.result.skipped).length, 4);
  assert(!r.runs.some(s => /Spitfire\.exe/i.test(s)), 'must not launch original application');
  assert(!r.runs.some(s => /(?:\blaunch\b|\bexit\b|\bretry\b|optout-on)/.test(s)), 'unsafe helper verb');
  assert(!r.runs.some(s => /readonly_ui\.exe" (regensvc|user)\b/.test(s)), 'no keyboard-driven access switching');
});
test('initial service display is preserved with one screen pass', () => {
  const r = rig({ access: 1 }); const v = r.run(); assert.equal(v.outcome, 'COMPLETED'); assert.equal(uiActions(r).length, 5); assert.equal(r.access, 1);
  assert.equal(v.actions.filter(a => !a.result.skipped).length, 5);
  assert(!r.runs.some(s => /readonly_ui\.exe" (regensvc|user)\b/.test(s)), 'service mode must not be toggled');
});
test('missing driver is provisioned and probed again', () => {
  const r = rig({ probeExit: 20 }); assert.equal(r.run().outcome, 'COMPLETED'); assert.equal(r.runs.filter(s => /provision_winpcap/.test(s)).length, 1); assert.equal(r.runs.filter(s => /--probe/.test(s)).length, 2);
});
test('existing incompatible driver is never replaced', () => {
  const r = rig({ probeExit: 21 }); const v = r.run(); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 0); assert(!r.runs.some(s => /provision_winpcap/.test(s)));
});
test('failed installation prevents capture and UI', () => {
  const r = rig({ probeExit: 20, installExit: 22 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 0); assert(!r.runs.some(s => /passive_capture.exe" [^\-]/.test(s)));
});
test('Opt-out OFF native preflight failure retains capture only', () => {
  const r = rig({ preflightExit: 20, optout: 0 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 0);
});
test('missing original native preflight failure retains capture only', () => {
  const r = rig({ preflightExit: 20 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 0);
});
test('no bidirectional traffic prevents every input action', () => {
  const r = rig({ ready: false }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 0);
});
test('two failed status reads retain the actual native timestamp without renewing it', () => {
  const r = rig(); reach(r, 'baseline');
  const original = r.context.lastStatus, tick = original.updated_tick;
  r.setStatusReadFailures(2);
  assert.strictEqual(r.context.status(), original);
  assert.strictEqual(r.context.status(), original);
  assert.equal(r.context.lastStatus.updated_tick, tick);
  assert.equal(r.context.statusMisses, 2);
  assert(r.context.refreshProof(original));
  assert(r.files[r.base+'\\proof.txt'].includes('updated_tick='+tick+'\r\n'));
  assert(r.context.status()); assert.equal(r.context.statusMisses, 0);
});
test('third consecutive status read failure stops further UI', () => {
  const r = rig(); reach(r, 'baseline'); r.setStatusReadFailures(Infinity);
  assert(r.context.status()); assert(r.context.status()); assert.strictEqual(r.context.status(), null);
  r.context.tick(); assert(r.files[r.base+'\\UI_STOP']); assert.equal(uiActions(r).length, 0);
  assert.equal(r.context.reason, 'CAPTURE_NOT_READY');
});
test('atomic publisher hard failure blocks input and never creates a valid proof', () => {
  const r = rig({ publishExit: 2 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
  assert.equal(uiActions(r).length, 0); assert(!r.files[r.base+'\\proof.txt']);
});
test('publisher sharing result preserves existing proof and refuses missing old proof', () => {
  const r = rig(); reach(r, 'baseline'); const s = r.context.lastStatus;
  r.setPublishExits([1]); assert.equal(r.context.refreshProof(s), false);
  r.setPublishExits([0]); assert.equal(r.context.refreshProof(s), true); const old = r.files[r.base+'\\proof.txt'];
  r.setPublishExits([1]); const newer = Object.assign({}, s, {updated_tick:s.updated_tick+300});
  assert.equal(r.context.refreshProof(newer), true); assert.equal(r.files[r.base+'\\proof.txt'], old);
});
test('generic runner failure signals an active UI child and capture immediately', () => {
  const r = rig({ actionDuration: 5000 }); reach(r, 'action'); const child = r.context.child;
  assert.equal(child.Status, 0); r.context.fail('MOCK_UNEXPECTED_FAILURE');
  assert(r.files[r.base+'\\UI_STOP']); assert(r.files[r.base+'\\STOP']);
  assert.equal(r.context.reason, 'MOCK_UNEXPECTED_FAILURE');
});
test('action timeout requests graceful stop before terminating the helper', () => {
  const r = rig({ actionDuration: 90000 }); reach(r, 'action'); const child = r.context.child;
  for (let i = 0; i < 200 && !r.context.timeoutRequested; i++) r.step();
  assert.equal(r.context.timeoutRequested, true); assert(r.files[r.base+'\\UI_STOP']);
  assert.equal(child.Status, 0); assert(!child.terminated, 'first timeout must permit key/button release');
  r.step(); r.step(); r.step(); r.step(); assert(!child.terminated, 'grace must last at least 1200 ms');
  for (let i = 0; i < 5 && !child.terminated; i++) r.step();
  assert(child.terminated); assert.equal(r.context.reason, 'ACTION_TIMEOUT');
});
test('observed state command stops subsequent UI', () => {
  const r = rig({ writeAfterAction: 1 }); const v = r.run(); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1); assert.equal(v.reason, 'STATE_COMMAND_OBSERVED');
});
test('UI guard failure stops subsequent actions', () => {
  const r = rig({ actionExit: 82 }); const v = r.run(); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1);
});
test('missing action result prevents successful completion', () => {
  const r = rig({ missingActionResult: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1);
});
test('changed original PID in action evidence stops subsequent UI', () => {
  const r = rig({ changedPid: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1);
});
test('Opt-out OFF in action evidence stops subsequent UI', () => {
  const r = rig({ actionOptoutOff: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1);
});
test('changed access mode in action evidence stops subsequent UI', () => {
  const r = rig({ changedAccess: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(uiActions(r).length, 1);
});
test('capture early failure is not a completed run', () => {
  const r = rig({ captureEarly: 1, captureExit: 23 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert(uiActions(r).length <= 1);
});
test('collector death stops an active UI child on the next poll despite fresh stale status', () => {
  const r = rig({ captureEarly: 1, captureExit: 23 });
  r.context.begin();
  for (let i = 0; i < 200 && r.context.stage !== 'action'; i++) r.step();
  assert.equal(r.context.stage, 'action');
  assert.equal(r.context.child.Status, 0, 'UI child must still be running');
  assert(r.files[r.base+'\\proof.txt'], 'a live capture initially authorized the action');
  r.step();
  assert.equal(r.context.cap.Status, 1, 'collector has now exited');
  assert.equal(r.context.child.Status, 0, 'test must inspect before the child completes');
  const oldStatus = JSON.parse(r.files[r.base+'\\capture\\status.json']);
  assert.equal(oldStatus.ui_ready, true, 'stale status deliberately still claims ready');
  assert.equal(r.context.reason, 'CAPTURE_ENDED_EARLY_23');
  assert(r.files[r.base+'\\UI_STOP'], 'stop signal must be written without waiting for child exit');
  assert(!r.files[r.base+'\\proof.txt'], 'last live proof must be withdrawn immediately');
  assert.equal(r.context.refreshProof(oldStatus), false, 'dead collector cannot renew a fresh-looking proof');
  for (let i = 0; i < 200 && !r.context.finished; i++) r.step();
  assert(r.context.finished);
  assert.equal(uiActions(r).length, 1);
  assert.equal(JSON.parse(r.files[r.base+'\\result.json']).outcome, 'PARTIAL_OR_BLOCKED');
});
test('capture final nonzero exit is not a completed run', () => {
  const r = rig({ captureExit: 23 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('missing capture summary is not a completed run', () => {
  const r = rig({ noSummary: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('capture output error is not a completed run', () => {
  const r = rig({ summaryIOError: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('missing final replies is not a completed run', () => {
  const r = rig({ summaryNoReply: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('failed PCAP reopening validation is not a completed run', () => {
  const r = rig({ pcapValidation: false }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('report error cannot leave result.json marked completed', () => {
  const r = rig({ reportFailure: true }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED');
});
test('explicit stop before any action prevents all inputs', () => {
  const r = rig(); r.context.begin(); r.step(); r.context.requestStop(); for (let i = 0; i < 100 && !r.context.finished; i++) r.step(); assert(r.context.finished); assert.equal(uiActions(r).length, 0); const v = JSON.parse(r.files[r.base+'\\result.json']); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED');
});
test('real field native86 remains an actionable failure, not missing evidence', () => {
  const field = fieldFixture('third-result.json');
  const r = rig({ preflightResult: field.preflight, actionExit: 86, actionResult: field.actions[0].result });
  const v = r.run();
  assert.equal(v.version, '1.1'); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED');
  assert.equal(v.reason, 'ACTION_GUARD_86'); assert.equal(uiActions(r).length, 1);
  assert.equal(v.actions[0].evidence_valid, true); assert.equal(v.failure.exit_code, 86);
  assert.equal(v.failure.failure_reason, 'menu_popup_unconfirmed');
  assert.equal(v.failure.timeline, 'actions/01-temperature/timeline.jsonl');
  assert(v.message_ko.includes('메뉴 항목 클릭 전에 중지'));
});
test('new native failure detail survives into the saved top-level result', () => {
  const field = fieldFixture('third-result.json');
  const native = Object.assign({}, field.actions[0].result, {failure_reason:'menu_popup_unconfirmed', failure_detail:'Popup geometry failed: actual 170x74; expected 193x68'});
  const r = rig({preflightResult:field.preflight, actionExit:86, actionResult:native});
  const v = r.run();
  assert.equal(v.failure.failure_detail, native.failure_detail);
  assert.equal(v.actions[0].failure.failure_detail, native.failure_detail);
  assert(r.files[r.base+'\\REPORT.txt'].includes(native.failure_detail));
});
test('real field preflight identifies the already open original auxiliary windows', () => {
  const field = fieldFixture('first-result.json');
  const windows = fs.readFileSync(path.join(fixtureDir, 'first-windows.jsonl'), 'utf8');
  const r = rig({preflightExit:20, preflightResult:field.preflight, preflightWindows:windows});
  const v = r.run();
  assert.equal(v.reason, 'PREFLIGHT_BLOCKED_20'); assert.equal(uiActions(r).length, 0);
  assert.equal(v.failure.failure_reason, 'initial_auxiliary_open');
  assert.deepEqual(v.failure.blocking_windows.map(w => w.title), ['Temperature Control','Timing and High Voltage','Empower Service','Active Faults']);
  assert(v.message_ko.includes('Empower Service'));
  assert.equal(v.failure.timeline, 'actions/00-preflight/timeline.jsonl');
});
test('missing optional window inventory does not hide a confirmed preflight failure', () => {
  const field = fieldFixture('first-result.json');
  const r = rig({preflightExit:20, preflightResult:field.preflight}); const v = r.run();
  assert.equal(v.reason, 'PREFLIGHT_BLOCKED_20'); assert.equal(v.failure.failure_reason, 'initial_auxiliary_open');
  assert.deepEqual(v.failure.blocking_windows, []);
});
test('native result exit0 cannot conceal a failed native process exit86', () => {
  const r = rig({actionExit:86, actionEvidenceOverrides:{exit_code:0}}); const v = r.run();
  assert.equal(v.reason, 'ACTION_EVIDENCE_UNCONFIRMED'); assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED');
  assert.equal(v.failure, null); assert.equal(v.actions[0].evidence_valid, false);
});
test('native failure result cannot be accepted when the process claims success', () => {
  const r = rig({actionEvidenceOverrides:{exit_code:86}}); const v = r.run();
  assert.equal(v.reason, 'ACTION_EVIDENCE_UNCONFIRMED'); assert.equal(uiActions(r).length, 1);
});
test('malformed action JSON is still unconfirmed evidence', () => {
  const r = rig({actionExit:86, actionRaw:'{broken json'}); const v = r.run();
  assert.equal(v.reason, 'ACTION_EVIDENCE_UNCONFIRMED'); assert.equal(v.failure, null);
});
test('action evidence for the wrong mode is rejected', () => {
  const r = rig({actionEvidenceOverrides:{mode:'timing'}}); const v = r.run();
  assert.equal(v.reason, 'ACTION_EVIDENCE_UNCONFIRMED'); assert.equal(uiActions(r).length, 1);
});
test('successful preflight requires a valid original identity and ready evidence', () => {
  const r = rig({preflightResult:{mode:'preflight',exit_code:0,preflight_ready:true,original_pid:0,emp_optout:1,gAccessLevel:0,original_left_running:true}});
  const v = r.run(); assert.equal(v.reason, 'PREFLIGHT_BLOCKED_0'); assert.equal(uiActions(r).length, 0); assert.equal(v.failure, null);
});
test('capture write detection stays primary over a simultaneous native UI failure', () => {
  const r = rig({writeAfterAction:1,actionExit:86,actionEvidenceOverrides:{failure_reason:'menu_popup_unconfirmed',failure_detail:'secondary UI failure'}});
  const v = r.run(); assert.equal(v.reason, 'STATE_COMMAND_OBSERVED'); assert.equal(v.failure, null);
  assert(v.message_ko.includes('값 변경 명령')); assert(!v.message_ko.includes('조회 메뉴'));
  assert.equal(v.actions[0].failure.failure_reason, 'menu_popup_unconfirmed');
});
test('status snapshot failures never read an old private copy as a fresh sample', () => {
  const r = rig(); reach(r, 'baseline');
  const previous = r.context.lastStatus, tick = previous.updated_tick, reads = r.statusPrivateReads;
  r.files[r.base+'\\capture-status.json'] = JSON.stringify({updated_tick:tick+999999, ui_ready:true, any_write_commands:0, observed_pairs:1});
  r.setSnapshotExits([1,2,1]);
  assert.strictEqual(r.context.status(), previous); assert.strictEqual(r.context.status(), previous);
  assert.strictEqual(r.context.status(), null);
  assert.equal(r.statusPrivateReads, reads, 'nonzero native exits must prevent FSO reads');
  assert.equal(r.context.lastStatus.updated_tick, tick, 'failed snapshots must not invent fresh timestamps');
  assert.equal(r.context.statusMisses, 3);
});
test('FSO status stream closes even when ReadAll throws', () => {
  const r = rig(); reach(r, 'baseline'); const closes = r.statusCloses, previous = r.context.lastStatus;
  r.setStatusReadAllFailures(1);
  assert.strictEqual(r.context.status(), previous); assert.equal(r.statusCloses, closes+1);
  assert(r.context.status()); assert.equal(r.context.statusMisses, 0);
});
test('status snapshot preserves source timestamp and source bytes', () => {
  const r = rig(); reach(r, 'baseline'); const sourcePath = r.base+'\\capture\\status.json';
  const sourceText = r.files[sourcePath], sourceTick = JSON.parse(sourceText).updated_tick;
  const s = r.context.status();
  assert.equal(r.files[sourcePath], sourceText); assert.equal(r.files[r.base+'\\capture-status.json'], sourceText);
  assert.equal(s.updated_tick, sourceTick);
});
test('native snapshot failure before any valid status prevents all UI input', () => {
  const r = rig({snapshotExit:2}); const v = r.run();
  assert.equal(v.outcome, 'PARTIAL_OR_BLOCKED'); assert.equal(v.reason, 'NO_UNIQUE_BIDIRECTIONAL_TRAFFIC');
  assert.equal(uiActions(r).length, 0);
});
test('snapshot helper is not launched before capture exists', () => {
  const r = rig(); r.context.begin(); r.step();
  assert(!r.runs.some(s => s.includes(' --snapshot ')));
});
let failed = 0;
for (const [name, f] of tests) { try { f(); process.stdout.write('PASS '+name+'\n'); } catch (e) { failed++; process.stdout.write('FAIL '+name+': '+e.message+'\n'); } }
process.stdout.write(JSON.stringify({ tests: tests.length, passed: tests.length-failed, failed })+'\n');
process.exitCode = failed ? 1 : 0;
