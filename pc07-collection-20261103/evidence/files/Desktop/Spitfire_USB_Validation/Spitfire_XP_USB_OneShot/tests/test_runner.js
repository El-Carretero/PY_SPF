/* Node-only mocked orchestration tests. Does not touch any Windows machine. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '..', 'runner.js'), 'utf8');

function rig(options) {
  const o = Object.assign({ probeExit: 0, installExit: 0, preflightExit: 0,
    optout: 1, access: 0, ready: true, captureExit: 0 }, options || {});
  let time = Date.UTC(2026, 10, 1), tickTime = 10000;
  let access = o.access, capture = null, currentChild = null, actionsStarted = 0;
  const files = {}, runs = [], ui = {}, processes = [], base = 'C:\\SpitfireLogs\\test';
  function fakeDate() { return new Date(time); }
  fakeDate.prototype = Date.prototype;
  const fileSystem = {
    CreateFolder() {}, FolderExists() { return true; },
    GetParentFolderName(p) { return p.slice(0, p.lastIndexOf('\\')); },
    FileExists(p) { return Object.prototype.hasOwnProperty.call(files, p); },
    CreateTextFile(p) { files[p] = ''; return { Write(s) { files[p] += s; }, WriteLine(s) { files[p] += s+'\r\n'; }, Close() {} }; },
    OpenTextFile(p, mode, create) {
      if (!Object.prototype.hasOwnProperty.call(files, p)) {
        if (!create) throw new Error('File missing: ' + p);
        files[p] = '';
      }
      return { ReadAll() { return files[p]; }, WriteLine(s) { files[p] += s+'\r\n'; }, Close() {} };
    },
    DeleteFile(p) { delete files[p]; },
    MoveFile(a, b) { files[b] = files[a]; delete files[a]; }
  };
  function put(p, value) { files[p] = JSON.stringify(value); }
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
    Run(s) { runs.push(s); },
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
          if (o.actionExit && actionsStarted === (o.failAction || 1)) p.ExitCode = o.actionExit;
        }
      } else throw new Error('Unexpected process: ' + command);
      currentChild = p;
      return p;
    }
  };
  const context = { Date: fakeDate, Math, Object, Array, isFinite, decodeURIComponent,
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
        if (p.mode === 'regensvc' && p.ExitCode === 0) access = 1;
        if (p.mode === 'user' && p.ExitCode === 0) access = 0;
        if (p.mode === 'preflight' || !o.missingActionResult) put(p.out + '\\result.json', { original_pid: p.mode !== 'preflight' && o.changedPid ? 4321 : 1234, preflight_ready: o.preflightExit === 0,
          emp_optout: p.mode !== 'preflight' && o.actionOptoutOff ? 0 : o.optout, gAccessLevel: access, exit_code: p.ExitCode, original_left_running: true });
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
  return { context, files, runs, processes, base, step, run, ui, get access() { return access; } };
}

const tests = [];
function test(name, f) { tests.push([name, f]); }
function uiActions(r) { return r.runs.filter(s => /readonly_ui\.exe" (?!preflight)/.test(s)); }
test('successful normal-user pass uses all twelve fixed actions and restores user', () => {
  const r = rig(); const v = r.run(); assert.equal(v.outcome, 'COMPLETED'); assert.equal(uiActions(r).length, 12); assert.equal(r.access, 0);
  assert(!r.runs.some(s => /Spitfire\.exe/i.test(s)), 'must not launch original application');
  assert(!r.runs.some(s => /(?:\blaunch\b|\bexit\b|\bretry\b|optout-on)/.test(s)), 'unsafe helper verb');
});
test('initial service display is preserved with one screen pass', () => {
  const r = rig({ access: 1 }); const v = r.run(); assert.equal(v.outcome, 'COMPLETED'); assert.equal(uiActions(r).length, 5); assert.equal(r.access, 1);
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
test('capture early failure is not a completed run', () => {
  const r = rig({ captureEarly: 1, captureExit: 23 }); assert.equal(r.run().outcome, 'PARTIAL_OR_BLOCKED'); assert(uiActions(r).length <= 1);
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
let failed = 0;
for (const [name, f] of tests) { try { f(); process.stdout.write('PASS '+name+'\n'); } catch (e) { failed++; process.stdout.write('FAIL '+name+': '+e.message+'\n'); } }
process.stdout.write(JSON.stringify({ tests: tests.length, passed: tests.length-failed, failed })+'\n');
process.exitCode = failed ? 1 : 0;
