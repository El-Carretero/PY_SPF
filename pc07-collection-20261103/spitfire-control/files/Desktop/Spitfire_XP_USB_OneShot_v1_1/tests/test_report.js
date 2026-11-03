/* Real report renderer, mocked only at the ADODB file boundary. No Windows access. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const base = path.join(__dirname, 'fixtures', 'report-field');
const source = fs.readFileSync(path.join(__dirname, '..', 'report.js'), 'utf8');
const fixture = name => JSON.parse(fs.readFileSync(path.join(base, name), 'utf8').replace(/^\uFEFF/, ''));
const clone = value => JSON.parse(JSON.stringify(value));

function render(result) {
  let output = '', saved = null, closes = 0;
  const context = {
    root: 'C:\\SpitfireLogs\\report-test',
    pad(n) { return n < 10 ? '0' + n : '' + n; },
    ActiveXObject: function(name) {
      assert.equal(name, 'ADODB.Stream');
      return {Open() {}, WriteText(value) { output += value; },
        SaveToFile(file, mode) { assert.equal(mode, 2); saved = file; },
        Close() { closes++; }};
    }
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  context.makeReport(result);
  assert.equal(saved, 'C:\\SpitfireLogs\\report-test\\REPORT.html');
  assert.equal(closes, 1);
  return output;
}
function diagnostic(stage, mode, native, name, detail) {
  const dir = stage === 'preflight' ? '00-preflight' : '01-' + mode;
  return {stage, mode, exit_code: native.exit_code, failure_reason: name,
    failure_detail: detail || '', context_reason: native.context_reason,
    preflight_reason: native.preflight_reason, blocking_windows: [],
    evidence_valid: true, timeline: 'actions/' + dir + '/timeline.jsonl',
    result_file: 'actions/' + dir + '/result.json'};
}
function fieldMenuFailure() {
  const r = fixture('third-result.json');
  assert.equal(r.actions[0].exit_code, 86);
  assert.equal(r.actions[0].result.exit_code, 86);
  r.reason = 'ACTION_GUARD_86';
  r.message_ko = '메뉴의 신원이나 항목 경계를 확인하지 못해 항목 클릭을 중지했습니다.';
  r.failure = diagnostic('action', 'temperature', r.actions[0].result,
    'menu_popup_unconfirmed', 'Expected CVI popup absent or capture stopped; no item click, no recovery key');
  r.actions[0].failure = clone(r.failure);
  r.actions[0].evidence_valid = true;
  return r;
}
function actionRow(html) {
  const table = html.split('<h2>화면 시험</h2>')[1].split('</table>')[0];
  return table.split('</tr>')[1];
}
const tests = [];
function test(name, fn) { tests.push([name, fn]); }

test('field fixtures preserve the exact collected bytes', () => {
  for (const f of fixture('provenance.json').files) {
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(base, f.file))).digest('hex'), f.sha256);
  }
});
test('field native86 retains its code, detailed reason and evidence links', () => {
  const r = fieldMenuFailure(), html = render(r);
  assert(html.includes('ACTION_GUARD_86'));
  assert(html.includes('menu_popup_unconfirmed'));
  assert(html.includes('자동화 종료 코드 <code>86</code>'));
  assert(html.includes('no item click, no recovery key'));
  assert(html.includes('href="actions/01-temperature/timeline.jsonl"'));
  assert(html.includes('href="actions/01-temperature/result.json"'));
  assert(actionRow(html).includes('중지/미완료 86'));
  assert(!html.includes('ACTION_EVIDENCE_UNCONFIRMED'));
});
test('field preflight stop identifies each already open original window', () => {
  const r = fixture('first-result.json');
  r.failure = diagnostic('preflight', 'preflight', r.preflight, 'initial_auxiliary_open');
  const windows = fs.readFileSync(path.join(base, 'first-windows.jsonl'), 'utf8').trim().split(/\r?\n/).map(JSON.parse);
  r.failure.blocking_windows = windows.filter(w => w.kind === 'window' && w.pid === r.preflight.original_pid && w.visible && w.text !== 'Spitfire').map(w => ({title: w.text, class: w.class, hwnd: w.hwnd}));
  const html = render(r);
  for (const name of ['Temperature Control', 'Timing and High Voltage', 'Empower Service', 'Active Faults']) assert(html.includes('<li>' + name + '</li>'));
  assert(html.includes('initial_auxiliary_open'));
  assert(html.includes('href="actions/00-preflight/timeline.jsonl"'));
  assert(html.includes('href="actions/00-preflight/result.json"'));
});
test('unconfirmed native data is not presented as a confirmed reason', () => {
  const r = fieldMenuFailure();
  r.reason = 'ACTION_EVIDENCE_UNCONFIRMED';
  r.failure.evidence_valid = false;
  r.failure.failure_detail = 'UNTRUSTED_ROOT_DETAIL';
  r.actions[0].evidence_valid = false;
  r.actions[0].failure.evidence_valid = false;
  r.actions[0].failure.failure_detail = 'UNTRUSTED_ACTION_DETAIL';
  const html = render(r);
  assert(html.includes('증거 미확인'));
  assert(!html.includes('UNTRUSTED_ROOT_DETAIL'));
  assert(!html.includes('UNTRUSTED_ACTION_DETAIL'));
  assert(!html.includes('세부 사유: <code>menu_popup_unconfirmed'));
});
test('native text and blocking window titles cannot inject HTML', () => {
  const r = fieldMenuFailure();
  r.failure.failure_reason = '<reason & "quoted">';
  r.failure.failure_detail = '<script>alert("bad")</script>';
  r.failure.blocking_windows = [{title: '<img src=x onerror="bad">', class: 'CVI', hwnd: 1}];
  const html = render(r);
  assert(html.includes('&lt;reason &amp; &quot;quoted&quot;&gt;'));
  assert(html.includes('&lt;script&gt;alert(&quot;bad&quot;)&lt;/script&gt;'));
  assert(html.includes('&lt;img src=x onerror=&quot;bad&quot;&gt;'));
  assert(!html.includes('<script>'));
  assert(!html.includes('<img src=x'));
});
test('diagnostic evidence links cannot point outside the known result tree', () => {
  const r = fieldMenuFailure();
  r.failure.timeline = 'javascript:alert(1)';
  r.failure.result_file = '../../sensitive.txt';
  r.actions[0].failure.timeline = 'file:///C:/Windows/test.exe';
  r.actions[0].failure.result_file = 'https://example.invalid/collect';
  const html = render(r);
  for (const x of ['javascript:', '../../sensitive', 'file:///', 'https://example.invalid']) assert(!html.includes(x));
  assert(html.includes('href="actions/01-temperature/timeline.jsonl"'));
});
test('access-mode mismatch is never displayed as completed', () => {
  const r = fieldMenuFailure();
  r.failure = null;
  r.actions[0].failure = null;
  r.actions[0].exit_code = 0;
  r.actions[0].result.exit_code = 0;
  r.actions[0].result.gAccessLevel = 1;
  const row = actionRow(render(r));
  assert(!row.includes('>완료<'));
  assert(row.includes('중지/미완료'));
});
test('missing preflight or false evidence flag cannot produce a completed row', () => {
  const r = fieldMenuFailure();
  r.failure = null;
  r.actions[0].failure = null;
  r.actions[0].exit_code = 0;
  r.actions[0].result.exit_code = 0;
  r.actions[0].evidence_valid = false;
  assert(actionRow(render(r)).includes('증거 미확인'));
  r.actions[0].evidence_valid = true;
  r.preflight.preflight_ready = false;
  assert(actionRow(render(r)).includes('중지/미완료'));
  r.preflight = null;
  assert(actionRow(render(r)).includes('중지/미완료'));
});
test('a partial report without a reason never uses the completed fallback', () => {
  const r = fieldMenuFailure();
  r.reason = ''; r.message_ko = ''; r.failure = null;
  const html = render(r);
  assert(html.includes('시험이 완료되지 않았습니다.'));
  assert(!html.includes('허용한 화면 탐색과 양방향 패킷 기록을 완료했습니다.'));
});
test('successful disabled setup remains a skip and keeps its file links', () => {
  const r = fieldMenuFailure();
  r.outcome = 'COMPLETED'; r.reason = ''; r.message_ko = ''; r.failure = null;
  const a = r.actions[0];
  a.mode = 'setup'; a.exit_code = 0; a.failure = null;
  a.result.exit_code = 0; a.result.skipped = true;
  const html = render(r);
  assert(actionRow(html).includes('사용 불가 / 생략'));
  assert(html.includes('href="actions/01-setup/result.json"'));
  assert(!html.includes('중단 코드:'));
});
test('unknown action names are escaped and do not create arbitrary file links', () => {
  const r = fieldMenuFailure();
  r.actions[0].mode = '<img src=x>';
  r.actions[0].failure = null;
  const row = actionRow(render(r));
  assert(row.includes('&lt;img src=x&gt;'));
  assert(!row.includes('<img'));
  assert(!row.includes('href='));
});

let passed = 0;
for (const [name, fn] of tests) {
  try { fn(); passed++; console.log('PASS ' + name); }
  catch (e) { console.error('FAIL ' + name); throw e; }
}
console.log(JSON.stringify({tests: tests.length, passed, failed: tests.length - passed}));
