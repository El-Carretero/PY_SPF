var queryNames={"1000":"*idn?","1001":"MIL:DIODE1:CURR?","1002":"MIL:DIODE2:CURR?","1003":"MIL:POW?","1004":"MIL:READ:DIODE1:CURR?","1005":"MIL:READ:DIODE2:CURR?","1006":"MIL:READ:POW?","1007":"EMP:READ:DIODE:CURR?","1008":"EMP:READ:POW?","1009":"EMP:DIODE:CURR?","1010":"EMP:QSW:PRF?","1011":"EMP:QSW:PWID?","1012":"EMP:QSW:SOURCE?","1013":"EMP:STB?","1014":"EMP:FAULT?","1015":"HED:STB?","1016":"EMP:VERSION?","1017":"HED:MOTOR:*IDN?","1018":"HED:MOTOR:SPEED?","1019":"TDG:STB?","1020":"TDG:VOLT?","1021":"TDG:HV:ON?","1022":"TDG:STAT:BWD?","1023":"TDG:STBH?","1024":"TDG:OSC:FREQ?","1025":"TDG:DIV?","1026":"TDG:DEL","1027":"TDG:BWD?","1028":"ECU:STB?","1029":"ECU:STBH?","1030":"ECU:READTEMP?","1031":"ECU:HUM?","1032":"ECU:TEMP?","1033":"ECUOPTOUT?","1034":"HED:VERS?","1035":"EMP:VERS?","1036":"TDG:VERS?","1037":"ECU:VERS?","1038":"*IDN?","1039":"TDG:STBH?","1040":"TDG:HV1:VOLT?","1041":"TDG:HV2:VOLT?","1042":"TDG:READ:HV1VOLT?","1043":"TDG:READ:HV2VOLT?","1044":"ECU:HUMOVERRIDE?","1045":"TDG:DEL1?","1046":"TDG:DEL2?","1047":"TDG:DEL3?","1048":"TDG:DEL4?","1049":"TDG:DEL5?","1050":"TDG:OSC:MODE?","1051":"TDG:TRIG:MODE?","1052":"TDG:DEL0?","1053":"TDG:TRIG:FREQ?","1054":"TDG:BWD?","1055":"TDG:READ:HV1CURR?","1056":"TDG:READ:HV2CURR?","1057":"ECU:STBH?","1058":"TDG:DEL1?","1059":"TDG:DEL2?","1060":"HED:MOTOR:SPEED?","1061":"TDG:HV:ON?","1062":"*IDN?","1063":"TDG:DEL1?","1064":"TDG:DEL2?","1065":"TDG:READ:OSCQUEST?","1066":"TDG:STBHFLT?","1067":"TDG:OSC:MODE?","1068":"EMPOPTOUT?","1069":"HEDOPTOUT?","1070":"EMP:SECRETMSG1?","1071":"EMP:SECRETMSG2?","1072":"EMP:SECRETMSG3?","1073":"EMP:SECRETMSG4?","1074":"EMP:SECRETMSG5?","1075":"EMP:SECRETMSG6?","1076":"EMP:SECRETMSG7?","1077":"EMP:LBOTEMP?","1078":"EMP:LBOBREAK?","1079":"TDG:TRIG?","1080":"TDG:OSC:SETMODE?","1081":"*IDN?","1082":"*IdN?","1083":"TDG:DELMON?","1084":"ECU:TECTEMP?","1085":"STATUS?","1086":"MONITOR?","1087":"TDG:FAULTOVERRIDE?","1088":"ECU:STBH?","1089":"COMSTATUS?"};
/* JScript 5.6 local report renderer loaded by RUN.hta. */
function html(s){return (''+s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function utf8(p,s){var a=new ActiveXObject('ADODB.Stream');a.Type=2;a.Charset='utf-8';a.Open();a.WriteText(s);a.SaveToFile(p,2);a.Close();}
function reportEvidenceLink(p,label){return typeof p=='string'&&/^actions\/[0-9]{2}-(preflight|temperature|timing|faults|setup|about)\/(timeline\.jsonl|result\.json)$/.test(p)?'<a href="'+html(p)+'">'+html(label)+'</a>':'';}
function reportFailure(f){
 if(!f)return '';
 if(f.evidence_valid!==true)return '<p>증거 미확인: 기록된 세부 사유를 확정할 수 없습니다.</p>';
 var n=f.failure_reason||f.context_reason||f.preflight_reason||'native_action_blocked',h='<p>세부 사유: <code>'+html(n)+'</code> · 자동화 종료 코드 <code>'+html(f.exit_code)+'</code></p>';
 if(f.failure_detail)h+='<p>'+html(f.failure_detail)+'</p>';
 var w=f.blocking_windows||[],i,count=0,rows='';
 for(i=0;i<w.length&&i<32;i++)if(w[i]&&typeof w[i]=='object'){rows+='<li>'+html(w[i].title||w[i].text||w[i]['class']||'제목 없는 창')+'</li>';count++;}
 if(count)h+='<p>입력을 막은 기존 창:</p><ul>'+rows+'</ul>';
 var t=reportEvidenceLink(f.timeline,'중단 시점의 동작 기록'),r=reportEvidenceLink(f.result_file,'원본 자동화 결과');
 if(t||r)h+='<p>'+t+(t&&r?' · ':'')+r+'</p>';
 return h;
}
function reportActionComplete(r,a){return a.evidence_valid!==false&&a.exit_code===0&&a.result&&r.preflight&&r.preflight.preflight_ready===true&&a.result.exit_code===0&&a.result.emp_optout===1&&a.result.original_pid===r.preflight.original_pid&&a.result.original_left_running===true&&a.result.gAccessLevel===r.preflight.gAccessLevel;}
function makeReport(r){
 var s=r.capture||{},h='<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>Spitfire 시험 결과</title><style>body{font-family:Arial,sans-serif;margin:30px;max-width:1100px;color:#172536}table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border:1px solid #ccd5de;padding:7px;text-align:left}th{background:#e8eff6}code{word-break:break-all}</style></head><body><h1>Spitfire 1회 자동시험 결과</h1>';
 h+='<p><b>'+html(r.outcome)+'</b> '+html(r.message_ko||r.reason||(r.outcome=='COMPLETED'?'허용한 화면 탐색과 양방향 패킷 기록을 완료했습니다.':'시험이 완료되지 않았습니다. 아래 기록을 확인하세요.'))+'</p>';
 if(r.reason)h+='<p>중단 코드: <code>'+html(r.reason)+'</code></p>';
 if(r.outcome!='COMPLETED')h+=reportFailure(r.failure);
 h+='<p>종료 시각: '+html(r.completed_utc)+' (XP 시계 기준 UTC). 이 보고서는 통신 상대가 실물인지 시뮬레이터인지 자동으로 판정하지 않습니다. 연결된 상대의 응답을 그대로 기록합니다.</p>';
 h+='<h2>캡처</h2><p>원본 송신 '+html(s.command_packets||0)+' / 상대 응답 '+html(s.response_packets||0)+' 패킷. 관찰한 상대 쌍 '+html(s.observed_pairs||0)+'. PCAP 구조 검사: '+html(s.pcap_validation_ok===true?'통과':'미확인 또는 실패')+'.</p>';
 h+='<p>IP: '+html(s.command_src_ip||'?')+' → '+html(s.controller_ip||'?')+'. 상태 변경 명령 감지 '+html(s.any_write_commands||0)+'. 드라이버 보고 드롭 '+html(s.capture_drops||0)+'.</p>';
 h+='<p><a href="capture/summary.json">상세 캡처 요약</a> · <a href="capture/packets.jsonl">원본 페이로드 기록</a> · <a href="timeline.jsonl">동작 타임라인</a> · <a href="result.json">전체 결과 JSON</a></p><ul>';
 var ad=s.adapters||[],i,t;for(i=0;i<ad.length;i++)if(ad[i].opened)h+='<li><a href="capture/adapter-'+pad(ad[i].interface_id)+'.pcap">adapter-'+pad(ad[i].interface_id)+'.pcap</a>: '+html(ad[i].frames)+' 프레임</li>';h+='</ul>';
 h+='<h2>화면 시험</h2><table><tr><th>동작</th><th>시작 / 종료 (UTC)</th><th>결과</th><th>증거</th></tr>';
 for(i=0;i<r.actions.length;i++){
  var a=r.actions[i],d='actions/'+pad(i+1)+'-'+a.mode,known=/^(temperature|timing|faults|setup|about)$/.test(a.mode),ok=reportActionComplete(r,a);
  h+='<tr><td>'+html(a.mode)+'</td><td>'+html(a.start)+'<br>'+html(a.end)+'</td><td>'+html(ok?(a.result.skipped?'사용 불가 / 생략':'완료'):(a.evidence_valid===false?'증거 미확인':('중지/미완료 '+(typeof a.exit_code=='number'?a.exit_code:'종료 코드 미기록'))))+reportFailure(a.failure)+'</td><td>';
  if(known)h+='<a href="'+html(d+'/timeline.jsonl')+'">동작 기록</a> · <a href="'+html(d+'/result.json')+'">자동화 결과</a> · <a href="'+html(d+'/desktop-before.bmp')+'">시작 화면</a> · <a href="'+html(d+'/desktop-after.bmp')+'">종료 화면</a>';
  h+='</td></tr>';
 }h+='</table>';
 h+='<h2>조회와 주기 통신</h2><p>각 UDP 패킷의 첫 번째 프로토콜 메시지를 기준으로 집계했습니다. 아래 주기는 해당 실행 구간에서 관찰한 값이며 실물 컨트롤러의 보장 사양을 뜻하지 않습니다.</p><table><tr><th>태그 / 원본 조회 이름</th><th>방향</th><th>수</th><th>평균 / 최소 / 최대 간격 (ms)</th></tr>';
 t=s.tag_statistics||[];for(i=0;i<t.length;i++){var z=t[i];h+='<tr><td>'+html(z.tag)+' '+html(queryNames[z.tag]||'')+'</td><td>'+html(z.kind)+'</td><td>'+html(z.count)+'</td><td>'+(z.periods_valid===false?'시계 역행으로 주기 미확인':html(z.mean_interval_us/1000)+' / '+html(z.min_interval_us/1000)+' / '+html(z.max_interval_us/1000))+'</td></tr>';}h+='</table>';
 h+='<h2>시험 범위와 제외 항목</h2><p>현재 화면, Temperature Control, Timing and High Voltage, Active Faults, Empower Setup, Help/About를 현재 표시 모드에서 확인합니다. 이미 서비스 모드인 경우 확장 화면을 수집합니다. 설정 입력이나 장비 명령 버튼은 누르지 않습니다. 서비스 모드 진입 및 복원용 문자 입력, 원본 프로그램 시작·종료·재시작·재접속, Laser RUN/ON/OFF, HV, 온도와 파라미터 편집, Opt-out 변경, fault reset, interlock 우회, 출처가 불명확한 버튼은 제외했습니다.</p>';
 h+='<p>시작 시 Opt-out이 OFF이면 자동으로 켜지 않고 화면 시험을 건너뜁니다. 버전·창·통신 검증이 실패하면 이후 입력을 중지합니다. 상태 변경 패킷 감지는 이미 전송된 명령을 차단하지 않으며, 중지 버튼도 레이저를 정지시키지 않습니다. 원본 프로그램은 계속 실행됩니다.</p>';
 h+='<p>사용자/서비스 표시 모드는 바꾸지 않습니다. Opt-out ON의 사용자 모드에서 비활성화되는 Empower Setup은 생략합니다. 기존 편집 컨트롤이나 불명확한 포커스가 있으면 자동 클릭을 수행하지 않습니다.</p>';
 h+='<p><a href="app/docs/CONTROLS.csv">컨트롤별 허용·제외 목록</a> · <a href="app/docs/README-KO.txt">실행 안내</a> · <a href="app/docs/capture-dependency-provenance.json">캡처 도구 출처·버전·무결성</a></p></body></html>';
 utf8(root+'\\REPORT.html',h);
}
