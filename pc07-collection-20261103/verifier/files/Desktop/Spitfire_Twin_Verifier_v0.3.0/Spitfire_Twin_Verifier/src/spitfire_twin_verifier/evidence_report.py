"""Headless-safe evidence summaries and escaped HTML/JSON reports."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import uuid


def evidence_rows(payload: dict) -> list[tuple[str, str, str, str]]:
    """Human-readable summaries without promoting a model pass to parity."""
    item = payload.get("result", payload)
    if not isinstance(item, dict):
        return [("결과", "상세 JSON 참조", "UNVERIFIED", str(item))]
    rows = []
    for client in item.get("clients", []):
        name = str(client.get("inspection", {}).get("version", "unknown"))
        for case in client.get("cases", []):
            failures = [", ".join(op.get("differences", [])) for op in case.get("operations", []) if op.get("differences")]
            rows.append((name, case.get("label", case.get("id", "")), case.get("status", "UNVERIFIED"),
                         case.get("detail", "; ".join(failures) or "transport/state fixture 시험")))
        if not client.get("cases"):
            rows.append((name, "클라이언트 실행", client.get("status", "UNVERIFIED"), client.get("detail", "")))
    if "model_verdict" in item:
        rows.append((item.get("name", "모델"), "합성 정책 자체 시험", item["model_verdict"], "실제 XP/Python 반응 시험 아님"))
        for assertion in item.get("assertions", []):
            rows.append((f"{assertion['at_ms']:g} ms", assertion["path"], "PASS" if assertion["passed"] else "FAIL",
                         f"기대 {assertion['expected']!r} / 실제 {assertion['actual']!r}"))
        rows.append(("동등성", "클라이언트 / 실제 하드웨어", "UNVERIFIED", "별도 측정과 관찰 필요"))
    if "inspection_status" in item:
        rows.append((item.get("version", "unknown"), "파일 정적 검사", item["inspection_status"], item.get("path", "")))
        rows.append(("실행", "정적 검사는 소스를 실행하지 않음", "NOT_PERFORMED", item.get("profile_id", "unknown")))
    if "error" in item:
        rows.append(("작업", "오류", "ERROR", str(item["error"])))
    return rows or [("범위", "상세 JSON 참조", "UNVERIFIED", str(item.get("scope", "실행 증거는 별도 시험으로 확인")))]


def write_workbench_report(directory: str | Path, payload: dict) -> Path:
    """Write an immutable, escaped snapshot; never overwrite an earlier run."""
    root = Path(directory).expanduser().resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = root / f"workbench_{stamp}_{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)
    snapshot = copy.deepcopy(payload)
    snapshot["exported_utc"] = datetime.now(timezone.utc).isoformat()
    text = json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)
    (output / "report.json").write_text(text, encoding="utf-8")
    rows = [row for run in snapshot.get("runs", [snapshot]) for row in evidence_rows(run)]
    table = '<table><tr><th>Version / time</th><th>Test</th><th>Result</th><th>Scope / difference</th></tr>' + ''.join(
        '<tr class="' + (row[2] if row[2] in {"PASS", "FAIL", "ERROR", "UNVERIFIED"} else "") + '">' +
        ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in row) + '</tr>' for row in rows) + '</table>'
    page = (
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Spitfire verification workbench</title>'
        '<style>body{font:16px system-ui;margin:32px;max-width:1200px;line-height:1.5}'
        'aside{background:#fff3d7;padding:16px;border-left:5px solid #8a4b00}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:20px}'
        'table{border-collapse:collapse;width:100%;margin-top:20px}td,th{border:1px solid #ccd2d7;padding:8px;text-align:left}'
        '.PASS td:nth-child(3){color:#18794e}.FAIL td:nth-child(3),.ERROR td:nth-child(3){color:#b42318}'
        '.UNVERIFIED td:nth-child(3){color:#8a4b00}</style>'
        '<h1>Spitfire version / scenario report</h1>'
        '<aside>Model PASS does not establish XP GUI compatibility, client reaction '
        'equivalence, or physical laser safety. Read the scope and limitations '
        'of each result. A selected version label is not executable evidence.</aside>'
        + table + '<h2>Recorded evidence</h2><pre>' + html.escape(text) + '</pre></html>'
    )
    (output / "report.html").write_text(page, encoding="utf-8")
    return output


