"""Standalone HTML/JSON comparison report generation."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any

from . import __version__
from .compare import ComparisonResult, compare_transactions
from .records import CaptureStore, CaptureSnapshot


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _ids(values: list[int]) -> str:
    return ", ".join(str(value) for value in values) or "—"


def render_html(result: ComparisonResult, metadata: dict[str, Any]) -> str:
    rows = []
    for row in result.rows:
        rows.append(
            f"<tr class='{_e(row.status.lower())}'><td>{_e(row.status)}</td>"
            f"<td>{_e(row.command_id or '—')}</td>"
            f"<td><code>{_e(row.original_command or '—')}</code></td>"
            f"<td><code>{_e(row.python_command or '—')}</code></td>"
            f"<td>{_e(row.original_response or '—')}</td>"
            f"<td>{_e(row.python_response or '—')}</td>"
            f"<td>{_e(row.note)}</td></tr>"
        )
    count_rows = "".join(
        f"<tr><td>{item['command_id']}</td><td>{item['original']}</td><td>{item['python']}</td></tr>"
        for item in result.count_differences
    ) or "<tr><td colspan='3'>차이 없음</td></tr>"
    verdict_class = "good" if result.verdict == "MATCH" else ("warn" if result.verdict == "INCOMPLETE" else "bad")
    created = metadata.get("created_utc", "")
    issue_rows = "".join(f"<tr><td>{_e(x.get('kind', ''))}</td><td>{_e(x.get('client', ''))}</td><td>{_e(x.get('note', ''))}</td></tr>" for x in result.issues)
    dimensions = {"명령·응답 내용": result.content_verdict, "의미 비교 (숫자 표기 정규화)": result.semantic_verdict,
                  "헤더·줄끝": result.framing_verdict, "전송 상태": result.transport_health,
                  "화면 확인": result.gui_verdict, "처리 중 패킷": result.pending_datagrams,
                  "프로그램 반응 규칙": result.client_reaction_verdict,
                  "물리적 장비 검증": result.physical_validation}
    dimension_rows = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in dimensions.items())
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spitfire Twin Verification Report</title>
<style>
:root{{--ink:#17202a;--muted:#637083;--line:#d8dee8;--panel:#fff;--bg:#f3f6fa;--blue:#215a9a;--good:#18794e;--bad:#b42318;--warn:#a15c00}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Segoe UI,Arial,sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}} h1{{margin:0 0 4px;font-size:28px}} h2{{margin-top:28px}}
.muted{{color:var(--muted)}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:22px 0}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}} .big{{font-size:25px;font-weight:700}}
.good{{color:var(--good)}} .bad{{color:var(--bad)}} .warn{{color:var(--warn)}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid var(--line)}} th,td{{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}
th{{position:sticky;top:0;background:#eaf0f7;z-index:1}} code{{white-space:pre-wrap}} .tablewrap{{overflow:auto;max-height:680px;border-radius:8px}}
tr.match td:first-child{{color:var(--good)}} tr:not(.match) td:first-child{{color:var(--bad);font-weight:700}}
.notice{{background:#fff8e6;border-left:4px solid #e0a100;padding:12px 14px;margin:18px 0}}
</style></head><body><main>
<h1>Spitfire Twin Verification Report</h1>
<div class="muted">Verifier v{_e(__version__)} · {_e(created)}</div>
<div class="notice"><b>판정 범위:</b> 이 보고서는 동일 스냅샷의 명령·응답 내용과 헤더·줄끝을 비교합니다. 배치 구성 차이는 별도로 기록합니다. MATCH는 관측한 정상 wire 증거의 일치입니다. 각 GUI가 화면에 표시한 값, 실제 인터록, 레이저 출력은 자동 검증하지 않습니다.</div>
<section class="cards">
 <div class="card"><div class="muted">Wire 판정</div><div class="big {verdict_class}">{_e(result.verdict)}</div></div>
 <div class="card"><div class="muted">시퀀스 유사도</div><div class="big">{result.sequence_similarity:.1%}</div></div>
 <div class="card"><div class="muted">완전 일치</div><div class="big good">{result.matched}</div></div>
 <div class="card"><div class="muted">차이</div><div class="big {'bad' if result.differences else 'good'}">{result.differences}</div></div>
</section>
<h2>판정 상세</h2><table>{dimension_rows}</table>
<h2>오류 및 미검증 항목</h2><table><tr><th>종류</th><th>클라이언트</th><th>설명</th></tr>{issue_rows or '<tr><td colspan="3">없음</td></tr>'}</table>
<h2>세션 개요</h2>
<table><thead><tr><th></th><th>{_e(result.original_label)}</th><th>{_e(result.python_label)}</th></tr></thead><tbody>
<tr><td>전체 트랜잭션</td><td>{result.original_total}</td><td>{result.python_total}</td></tr>
<tr><td>쓰기 명령 수</td><td>{result.original_writes}</td><td>{result.python_writes}</td></tr>
<tr><td>관측 Query ID</td><td>{_e(_ids(result.original_query_ids))}</td><td>{_e(_ids(result.python_query_ids))}</td></tr>
<tr><td>관측 Write ID</td><td>{_e(_ids(result.original_write_ids))}</td><td>{_e(_ids(result.python_write_ids))}</td></tr>
<tr><td>반복 폴링 coverage 차이</td><td colspan="2">{_e(_ids(result.poll_coverage_differences))}</td></tr>
</tbody></table>
<h2>횟수 차이 <span class="muted">(자동 폴링 주기 차이 포함)</span></h2>
<table><thead><tr><th>Command ID</th><th>XP 원본</th><th>Python</th></tr></thead><tbody>{count_rows}</tbody></table>
<h2>정렬된 명령·응답 비교</h2>
<p class="muted">폴링 반복 압축: {_e(result.ignored_polling)}. 동일한 연속 관측만 압축합니다. 응답·오류·상태 전이는 비교에 남습니다. 반복 횟수는 위 표에서 확인합니다.</p>
<div class="tablewrap"><table><thead><tr><th>상태</th><th>ID</th><th>XP 원본 명령</th><th>Python 명령</th><th>XP 응답</th><th>Python 응답</th><th>설명</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="7">비교 가능한 트랜잭션이 없습니다.</td></tr>'}</tbody></table></div>
<h2>재현 정보</h2><pre>{_e(json.dumps(metadata, ensure_ascii=False, indent=2))}</pre>
</main></body></html>"""


def write_report(output_root: Path, result: ComparisonResult,
                 capture: CaptureStore | CaptureSnapshot,
                 metadata: dict[str, Any] | None = None) -> Path:
    # Never export an old cached verdict alongside a newer capture.
    snapshot = capture.snapshot() if isinstance(capture, CaptureStore) else capture
    result = compare_transactions(snapshot, result.original_label, result.python_label,
                                  ignore_polling=result.ignored_polling)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    directory = output_root / f"comparison_{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    details = dict(metadata or {})
    details.update(snapshot.metadata)
    details.update(created_utc=snapshot.created_utc, verifier_version=__version__,
                   session_id=snapshot.session_id, snapshot_transactions=len(snapshot.transactions),
                   pending_datagrams=list(snapshot.pending), batching=result.batching,
                   scope="fixture wire evidence; GUI observations are manual; no firmware/physical certification")
    (directory / "report.json").write_text(
        json.dumps({"metadata": details, "comparison": result.to_dict()}, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "report.html").write_text(render_html(result, details), encoding="utf-8")
    snapshot.save_jsonl(directory / "capture.jsonl")
    with (directory / "ui_observations.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scenario", "field", "expected", "XP original display", "Python display", "same?", "notes"])
        observations = snapshot.metadata.get("ui_observations", [])
        for item in observations:
            # Spreadsheet formula injection is not useful evidence.
            row = [item.get(key, "") for key in ("scenario", "field", "expected", "original", "python", "same", "notes")]
            writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for v in row])
        if not observations:
            writer.writerow(["Q-switch", "1250 Hz 설정 후 표시", "1250 Hz", "", "", "", "직접 관찰 후 입력"])
    return directory
