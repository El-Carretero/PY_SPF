/* XP-safe, read-only Spitfire VM evidence helper.
 * No UI activation, no process launch, no configuration writes.
 * Only network operation: explicitly guarded diagnostic EMPOPTOUT? query.
 * Build: see build_guest_probe.sh. Requires Windows XP SP3 (32-bit) or later.
 */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <tlhelp32.h>
#include <psapi.h>
/* Explicit legacy MSVCRT declarations avoid Zig's UCRT header wrappers. */
typedef struct probe_FILE FILE;
__declspec(dllimport) FILE * __cdecl fopen(const char*,const char*);
__declspec(dllimport) int __cdecl fclose(FILE*);
__declspec(dllimport) int __cdecl fflush(FILE*);
__declspec(dllimport) int __cdecl fprintf(FILE*,const char*,...);
__declspec(dllimport) int __cdecl printf(const char*,...);
__declspec(dllimport) int __cdecl fputs(const char*,FILE*);
__declspec(dllimport) int __cdecl fputc(int,FILE*);
__declspec(dllimport) char* __cdecl fgets(char*,int,FILE*);
__declspec(dllimport) size_t __cdecl fwrite(const void*,size_t,size_t,FILE*);
__declspec(dllimport) int __cdecl _snprintf(char*,size_t,const char*,...);
__declspec(dllimport) LPWSTR* WINAPI CommandLineToArgvW(LPCWSTR,int*);
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>

static char outdir[MAX_PATH];
static FILE *timeline, *winfile;
static int window_count;
static int original_running;
static const char *guest_ip="10.19.70.2", *sim_ip="10.19.70.13";
static void utc(char *s,size_t n) {
 SYSTEMTIME t; GetSystemTime(&t);
 _snprintf(s,n,"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds); s[n-1]=0;
}
static void js(FILE *f,const char *s) {
 const unsigned char *p=(const unsigned char*)s; fputc('"',f);
 for(;*p;p++) { if(*p=='"'||*p=='\\'){fputc('\\',f);fputc(*p,f);} else if(*p<32)fprintf(f,"\\u%04x",*p);else fputc(*p,f); }
 fputc('"',f);
}
static void jw(FILE *f,const WCHAR *w) {
 static char b[8192]; int n=WideCharToMultiByte(CP_UTF8,0,w,-1,b,sizeof(b),NULL,NULL);
 if(!n) strcpy(b,"<unicode conversion error>");js(f,b);
}
static FILE *openout(const char *leaf,const char *mode) {
 char p[MAX_PATH]; if(strlen(outdir)+strlen(leaf)+2>=sizeof(p))return NULL;
 _snprintf(p,sizeof(p),"%s\\%s",outdir,leaf);return fopen(p,mode);
}
static void event(const char *action,const char *phase,const char *detail,int code) {
 char t[40];utc(t,sizeof(t));
 if(timeline) { fputs("{\"utc_guest_clock\":",timeline);js(timeline,t);fputs(",\"action\":",timeline);js(timeline,action);fputs(",\"phase\":",timeline);js(timeline,phase);fputs(",\"detail\":",timeline);js(timeline,detail);fprintf(timeline,",\"code\":%d}\n",code);fflush(timeline); }
 printf("%s %s %s: %s (%d)\n",t,action,phase,detail,code);
}
static void window_text(HWND h,WCHAR *b,int cap) {
 DWORD_PTR result=0; b[0]=0;
 if(!SendMessageTimeoutW(h,WM_GETTEXT,(WPARAM)cap,(LPARAM)b,SMTO_ABORTIFHUNG|SMTO_BLOCK,200,&result)) GetWindowTextW(h,b,cap);
 b[cap-1]=0;
}
static void menus(HWND owner,HMENU menu,int depth) {
 int n,i; if(!menu||depth>12)return; n=GetMenuItemCount(menu);if(n>256)n=256;
 for(i=0;i<n;i++) {
  WCHAR text[1024];HMENU sub=GetSubMenu(menu,i);text[0]=0;GetMenuStringW(menu,i,text,1024,MF_BYPOSITION);
  fprintf(winfile,"{\"kind\":\"menu_item\",\"owner_hwnd\":%lu,\"hmenu\":%lu,\"depth\":%d,\"position\":%d,\"id\":%u,\"state\":%u,\"submenu\":%lu,\"text\":",(unsigned long)(uintptr_t)owner,(unsigned long)(uintptr_t)menu,depth,i,GetMenuItemID(menu,i),GetMenuState(menu,i,MF_BYPOSITION),(unsigned long)(uintptr_t)sub);jw(winfile,text);fputs("}\n",winfile);
  menus(owner,sub,depth+1);
 }
}
static void window_record(HWND h,int child) {
 static WCHAR title[2048];WCHAR cls[256];DWORD pid=0;RECT r={0,0,0,0};
 window_text(h,title,2048);GetClassNameW(h,cls,256);GetWindowThreadProcessId(h,&pid);GetWindowRect(h,&r);
 fprintf(winfile,"{\"kind\":\"%s\",\"hwnd\":%lu,\"parent_hwnd\":%lu,\"pid\":%lu,\"visible\":%s,\"enabled\":%s,\"control_id\":%d,\"style\":%lu,\"rect\":[%ld,%ld,%ld,%ld],\"class\":",child?"child":"window",(unsigned long)(uintptr_t)h,(unsigned long)(uintptr_t)GetParent(h),(unsigned long)pid,IsWindowVisible(h)?"true":"false",IsWindowEnabled(h)?"true":"false",GetDlgCtrlID(h),(unsigned long)GetWindowLong(h,GWL_STYLE),r.left,r.top,r.right,r.bottom);
 jw(winfile,cls);fputs(",\"text\":",winfile);jw(winfile,title);fputs("}\n",winfile);
}
static BOOL CALLBACK child_cb(HWND h,LPARAM x) { (void)x;if(++window_count>6000)return FALSE;window_record(h,1);return TRUE; }
static BOOL CALLBACK top_cb(HWND h,LPARAM x) { (void)x;if(++window_count>6000)return FALSE;window_record(h,0);menus(h,GetMenu(h),0);EnumChildWindows(h,child_cb,0);return TRUE; }
static int inventory_windows(void) {
 winfile=openout("windows.jsonl","wb");if(!winfile)return 0;
 window_count=0;EnumWindows(top_cb,0);fclose(winfile);winfile=NULL;return 1;
}
static int processes(void) {
 HANDLE snap;PROCESSENTRY32W p;FILE*f=openout("processes.jsonl","wb");if(!f)return 0;
 snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);if(snap==INVALID_HANDLE_VALUE){fclose(f);return 0;}
 ZeroMemory(&p,sizeof(p));p.dwSize=sizeof(p);
 if(Process32FirstW(snap,&p))do {
  static WCHAR path[2048];HANDLE h=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,p.th32ProcessID);DWORD error=0;path[0]=0;
  if(h){if(!GetModuleFileNameExW(h,NULL,path,2048))error=GetLastError();CloseHandle(h);}else error=GetLastError();
  if(_wcsicmp(p.szExeFile,L"SPITFIRE.EXE")==0)original_running=1;
  fprintf(f,"{\"pid\":%lu,\"parent_pid\":%lu,\"exe\":",(unsigned long)p.th32ProcessID,(unsigned long)p.th32ParentProcessID);jw(f,p.szExeFile);fputs(",\"path\":",f);jw(f,path);fprintf(f,",\"path_error\":%lu}\n",(unsigned long)error);
 }while(Process32NextW(snap,&p));
 CloseHandle(snap);fclose(f);return 1;
}
static int screenshot(void) {
 HDC screen=NULL,mem=NULL;HBITMAP bmp=NULL;HGDIOBJ old=NULL;BITMAPINFO bi;BITMAPFILEHEADER head;void*bits=NULL;FILE*f=NULL;int ok=0;
 int x=GetSystemMetrics(SM_XVIRTUALSCREEN),y=GetSystemMetrics(SM_YVIRTUALSCREEN),w=GetSystemMetrics(SM_CXVIRTUALSCREEN),h=GetSystemMetrics(SM_CYVIRTUALSCREEN);
 if(w<=0||h<=0||w>16384||h>16384)return 0;
 ZeroMemory(&bi,sizeof(bi));bi.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);bi.bmiHeader.biWidth=w;bi.bmiHeader.biHeight=-h;bi.bmiHeader.biPlanes=1;bi.bmiHeader.biBitCount=24;bi.bmiHeader.biCompression=BI_RGB;bi.bmiHeader.biSizeImage=(DWORD)(((w*3+3)&~3)*h);
 screen=GetDC(NULL);if(!screen)goto done;mem=CreateCompatibleDC(screen);if(!mem)goto done;
 bmp=CreateDIBSection(screen,&bi,DIB_RGB_COLORS,&bits,NULL,0);if(!bmp||!bits)goto done;old=SelectObject(mem,bmp);
 if(!BitBlt(mem,0,0,w,h,screen,x,y,SRCCOPY|CAPTUREBLT))goto done;
 ZeroMemory(&head,sizeof(head));head.bfType=0x4d42;head.bfOffBits=sizeof(head)+sizeof(BITMAPINFOHEADER);head.bfSize=head.bfOffBits+bi.bmiHeader.biSizeImage;
 f=openout("desktop.bmp","wb");if(!f)goto done;
 ok=fwrite(&head,1,sizeof(head),f)==sizeof(head)&&fwrite(&bi.bmiHeader,1,sizeof(BITMAPINFOHEADER),f)==sizeof(BITMAPINFOHEADER)&&fwrite(bits,1,bi.bmiHeader.biSizeImage,f)==bi.bmiHeader.biSizeImage;
 done:if(f)fclose(f);if(old)SelectObject(mem,old);if(bmp)DeleteObject(bmp);if(mem)DeleteDC(mem);if(screen)ReleaseDC(NULL,screen);return ok;
}
static void ipstr(DWORD value,char b[32]) {struct in_addr a;a.s_addr=value;strncpy(b,inet_ntoa(a),31);b[31]=0;}
static int network_inventory(void) {
 ULONG size=0;DWORD rc;IP_ADAPTER_INFO *all=NULL,*a;MIB_IPFORWARDTABLE*routes=NULL;MIB_IPADDRTABLE*ips=NULL;
 DWORD index=0,expect=inet_addr(guest_ip),target=inet_addr(sim_ip),i;int active=0,found=0,ok=1;FILE*f=openout("network.jsonl","wb");if(!f)return 0;
 rc=GetAdaptersInfo(NULL,&size);if(rc!=ERROR_BUFFER_OVERFLOW){ok=0;goto done;}
 all=(IP_ADAPTER_INFO*)malloc(size);if(!all||GetAdaptersInfo(all,&size)!=NO_ERROR){ok=0;goto done;}
 for(a=all;a;a=a->Next) {
  IP_ADDR_STRING*p;MIB_IFROW row;int isactive=0,hasip=0,match=0,badip=0;ZeroMemory(&row,sizeof(row));row.dwIndex=a->Index;rc=GetIfEntry(&row);
  for(p=&a->IpAddressList;p;p=p->Next)if(strcmp(p->IpAddress.String,"0.0.0.0")){hasip=1;if(!strcmp(p->IpAddress.String,guest_ip))match=1;else badip=1;}
  isactive=rc==NO_ERROR&&row.dwAdminStatus==1&&row.dwOperStatus==5&&hasip&&a->Type!=MIB_IF_TYPE_LOOPBACK;
  fprintf(f,"{\"kind\":\"adapter\",\"index\":%lu,\"type\":%u,\"admin_status\":%lu,\"oper_status\":%lu,\"if_error\":%lu,\"active\":%s,\"name\":",(unsigned long)a->Index,a->Type,(unsigned long)row.dwAdminStatus,(unsigned long)row.dwOperStatus,(unsigned long)rc,isactive?"true":"false");js(f,a->AdapterName);fputs(",\"description\":",f);js(f,a->Description);fputs(",\"ips\":[",f);
  for(p=&a->IpAddressList;p;p=p->Next){if(p!=&a->IpAddressList)fputc(',',f);fputs("{\"ip\":",f);js(f,p->IpAddress.String);fputs(",\"mask\":",f);js(f,p->IpMask.String);fputc('}',f);if(isactive&&!strcmp(p->IpAddress.String,guest_ip)&&(expect&inet_addr(p->IpMask.String))!=(target&inet_addr(p->IpMask.String)))ok=0;}
  fputs("],\"gateways\":[",f);for(p=&a->GatewayList;p;p=p->Next){if(p!=&a->GatewayList)fputc(',',f);js(f,p->IpAddress.String);if(isactive&&p->IpAddress.String[0]&&strcmp(p->IpAddress.String,"0.0.0.0"))ok=0;}fputs("]}\n",f);
  if(isactive){active++;if(match&&!badip){found++;index=a->Index;}else ok=0;}
  if(rc!=NO_ERROR)ok=0;
 }
 if(active!=1||found!=1)ok=0;
 size=0;rc=GetIpAddrTable(NULL,&size,FALSE);if(rc!=ERROR_INSUFFICIENT_BUFFER){ok=0;goto done;}ips=(MIB_IPADDRTABLE*)malloc(size);if(!ips||GetIpAddrTable(ips,&size,FALSE)!=NO_ERROR){ok=0;goto done;}
 for(i=0;i<ips->dwNumEntries;i++){char ip[32],mask[32];ipstr(ips->table[i].dwAddr,ip);ipstr(ips->table[i].dwMask,mask);fprintf(f,"{\"kind\":\"ip\",\"index\":%lu,\"ip\":",(unsigned long)ips->table[i].dwIndex);js(f,ip);fputs(",\"mask\":",f);js(f,mask);fputs("}\n",f);}
 size=0;rc=GetIpForwardTable(NULL,&size,FALSE);if(rc!=ERROR_INSUFFICIENT_BUFFER){ok=0;goto done;}routes=(MIB_IPFORWARDTABLE*)malloc(size);if(!routes||GetIpForwardTable(routes,&size,FALSE)!=NO_ERROR){ok=0;goto done;}
 for(i=0;i<routes->dwNumEntries;i++) {
  MIB_IPFORWARDROW*r=&routes->table[i];char dest[32],mask[32],hop[32];int loop=((ntohl(r->dwForwardDest)>>24)==127);
  if(r->dwForwardDest==expect&&r->dwForwardMask==0xffffffffu&&(ntohl(r->dwForwardNextHop)>>24)==127){MIB_IFROW lr;ZeroMemory(&lr,sizeof(lr));lr.dwIndex=r->dwForwardIfIndex;if(GetIfEntry(&lr)==NO_ERROR&&lr.dwType==MIB_IF_TYPE_LOOPBACK)loop=1;}
  ipstr(r->dwForwardDest,dest);ipstr(r->dwForwardMask,mask);ipstr(r->dwForwardNextHop,hop);
  fprintf(f,"{\"kind\":\"route\",\"index\":%lu,\"destination\":",(unsigned long)r->dwForwardIfIndex);js(f,dest);fputs(",\"mask\":",f);js(f,mask);fputs(",\"next_hop\":",f);js(f,hop);fprintf(f,",\"type\":%lu,\"metric\":%lu}\n",(unsigned long)r->dwForwardType,(unsigned long)r->dwForwardMetric1);
  if(r->dwForwardType==MIB_IPROUTE_TYPE_INVALID)continue;
  if(r->dwForwardDest==0&&r->dwForwardMask==0)ok=0;
  if(!loop&&(r->dwForwardIfIndex!=index||(r->dwForwardNextHop!=0&&r->dwForwardNextHop!=expect)))ok=0;
 }
 {MIB_IPFORWARDROW best;ZeroMemory(&best,sizeof(best));rc=GetBestRoute(target,expect,&best);if(rc!=NO_ERROR||best.dwForwardIfIndex!=index||(best.dwForwardNextHop!=0&&best.dwForwardNextHop!=expect))ok=0;fprintf(f,"{\"kind\":\"best_route_check\",\"error\":%lu,\"index\":%lu}\n",(unsigned long)rc,(unsigned long)best.dwForwardIfIndex);}
 done:fprintf(f,"{\"kind\":\"local_isolation_check\",\"ok\":%s,\"active_interfaces\":%d,\"matching_interfaces\":%d}\n",ok?"true":"false",active,found);free(all);free(routes);free(ips);fclose(f);return ok;
}
static int guard(const char *path) {
 static const char *required[]={"schema=spitfire-isolation-v1","vm_host=20255566-p07","vm_network=hostonly","host_ip_forwarding=disabled","host_ics_on_vmnet1=disabled","host_bridge_on_vmnet1=absent","physical_passthrough=absent","simulator_bind=10.19.70.13:1024","simulator_peer=10.19.70.2","simulator_immutable=true","guest_ip=10.19.70.2","authorization=diagnostic-optout-query-only"};
 unsigned int found=0,i;char line[1024];FILE*f=path?fopen(path,"rb"):NULL;int stamp=0;FILE*copy;
 if(!f)return 0;copy=openout("host-isolation-proof.txt","wb");
 while(fgets(line,sizeof(line),f)){if(copy)fputs(line,copy);line[strcspn(line,"\r\n")]=0;for(i=0;i<sizeof(required)/sizeof(required[0]);i++)if(!strcmp(line,required[i]))found|=(1u<<i);if(!strncmp(line,"verified_utc=",13)&&strlen(line)>=33)stamp=1;}
 fclose(f);if(copy)fclose(copy);return found==((1u<<(sizeof(required)/sizeof(required[0])))-1)&&stamp;
}
static int binary_save(const char *name,const char *data,size_t n) {FILE*f=openout(name,"wb");int ok;if(!f)return 0;ok=fwrite(data,1,n,f)==n;fclose(f);return ok;}
static int query_optout(void) {
 const char packet[]="Spectra-Physics:CMD_ECLIPSE,[1068]EMPOPTOUT?\n";
 const char prefix[]="Spectra-Physics:REPLY_ECLIPSE:";
 SOCKET s=INVALID_SOCKET;struct sockaddr_in local,remote,from;int flen=sizeof(from),n,result=21;static char buffer[4096];char *p,*end;DWORD timeout=3500;BOOL exclusive=TRUE;FILE*f;
 event("diagnostic_optout_query","begin","DIAGNOSTIC-GENERATED; not original SPITFIRE.EXE traffic",0);
 if(original_running){event("diagnostic_optout_query","blocked","SPITFIRE.EXE already running; no port reuse or traffic injection",21);return 21;}
 s=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);if(s==INVALID_SOCKET)goto done;
 if(setsockopt(s,SOL_SOCKET,SO_EXCLUSIVEADDRUSE,(const char*)&exclusive,sizeof(exclusive))==SOCKET_ERROR)goto done;
 if(setsockopt(s,SOL_SOCKET,SO_RCVTIMEO,(const char*)&timeout,sizeof(timeout))==SOCKET_ERROR)goto done;
 ZeroMemory(&local,sizeof(local));local.sin_family=AF_INET;local.sin_addr.s_addr=inet_addr(guest_ip);local.sin_port=htons(1024);
 if(bind(s,(struct sockaddr*)&local,sizeof(local))==SOCKET_ERROR)goto done;
 ZeroMemory(&remote,sizeof(remote));remote.sin_family=AF_INET;remote.sin_addr.s_addr=inet_addr(sim_ip);remote.sin_port=htons(1024);
 if(!binary_save("diagnostic-tx-payload.bin",packet,sizeof(packet)-1))goto done;
 n=sendto(s,packet,sizeof(packet)-1,0,(struct sockaddr*)&remote,sizeof(remote));if(n!=(int)sizeof(packet)-1)goto done;
 event("diagnostic_optout_query","sent","10.19.70.2:1024 -> 10.19.70.13:1024; query1068 only",n);
 n=recvfrom(s,buffer,sizeof(buffer)-1,0,(struct sockaddr*)&from,&flen);if(n<=0)goto done;
 binary_save("diagnostic-rx-payload.bin",buffer,(size_t)n);buffer[n]=0;
 if(from.sin_addr.s_addr!=remote.sin_addr.s_addr||from.sin_port!=remote.sin_port)goto done;
 if(n<(int)strlen(prefix)||memcmp(buffer,prefix,strlen(prefix)))goto done;
 p=buffer+strlen(prefix);if(strncmp(p,"<1068>",6))goto done;p+=6;
 while(*p==' '||*p=='\t')p++;if(*p!='0'&&*p!='1')goto done;result=(*p=='1')?0:20;end=p+1;
 while(*end==' '||*end=='\t'||*end=='\r'||*end=='\n')end++;
 if(end!=buffer+n)result=21;
 done:
 if(s!=INVALID_SOCKET)closesocket(s);
 f=openout("eligibility.json","wb");if(f){fputs("{\"evidence_source\":\"diagnostic-generated UDP, not original application\",\"simulator_response_not_physical_controller\":true,\"optout\":",f);fputs(result==0?"1":result==20?"0":"null",f);fprintf(f,",\"eligible_for_later_reviewed_suite\":%s,\"original_launched\":false,\"exit_code\":%d}\n",result==0?"true":"false",result);fclose(f);}
 event("diagnostic_optout_query",result==0?"end":"blocked",result==0?"Opt-out readback1; helper does not launch application":result==20?"Opt-out readback0; requested Opt-out-on suite blocked; no changes made":"Unknown/invalid/no Opt-out reply; suite blocked; no changes made",result);
 return result;
}
static int probe_main(int argc,char**argv) {
 WSADATA wsa;int preflight=0,netok,exitcode=0;const char*proof=NULL;char t[40];FILE*f;
 if(argc<3||((strcmp(argv[1],"inventory")&&strcmp(argv[1],"preflight")))){printf("Usage: guest_probe.exe inventory OUTDIR\n       guest_probe.exe preflight OUTDIR HOST_ISOLATION_PROOF.txt\nNever launches SPITFIRE.EXE or activates UI.\n");return 2;}
 preflight=!strcmp(argv[1],"preflight");if(preflight&&argc!=4)return 2;if(argc>3)proof=argv[3];
 if(strlen(argv[2])>MAX_PATH-64)return 2;strcpy(outdir,argv[2]);
 /* New directory required: never overwrite evidence from an earlier run. */
 if(!CreateDirectoryA(outdir,NULL)){printf("Output directory must be new and parent must exist; Win32 error %lu\n",(unsigned long)GetLastError());return 3;}
 timeline=openout("timeline.jsonl","wb");if(!timeline)return 3;
 event("inventory","begin","Read-only XP guest evidence; timestamps use guest UTC clock",0);
 if(WSAStartup(MAKEWORD(2,2),&wsa)){event("inventory","failed","Winsock initialization failed; no network activity",4);fclose(timeline);return 4;}
 utc(t,sizeof(t));f=openout("identity.json","wb");if(f){char computer[256]={0};DWORD len=sizeof(computer);OSVERSIONINFOA os;ZeroMemory(&os,sizeof(os));os.dwOSVersionInfoSize=sizeof(os);GetVersionExA(&os);GetComputerNameA(computer,&len);fputs("{\"helper_version\":\"1.0\",\"computer\":",f);js(f,computer);fputs(",\"utc_guest_clock\":",f);js(f,t);fprintf(f,",\"os_major\":%lu,\"os_minor\":%lu,\"build\":%lu,\"process_id\":%lu,\"no_ui_mutations\":true,\"no_application_launch\":true}\n",(unsigned long)os.dwMajorVersion,(unsigned long)os.dwMinorVersion,(unsigned long)os.dwBuildNumber,(unsigned long)GetCurrentProcessId());fclose(f);}
 if(!processes()){event("process_inventory","failed","Process enumeration failed",1);exitcode=4;}
 if(!inventory_windows()){event("window_inventory","failed","Window inventory file failed",1);exitcode=4;}
 if(!screenshot()){event("screenshot","failed","Desktop capture failed",1);exitcode=4;}else event("screenshot","end","desktop.bmp saved; no mouse/keyboard actions",0);
 netok=network_inventory();event("local_network_check",netok?"end":"blocked",netok?"Exactly expected active IPv4 interface; no gateway/default route; direct simulator route":"Expected local isolation conditions not met; see network.jsonl",netok?0:22);
 event("inventory","end",original_running?"Original SPITFIRE.EXE process observed":"No SPITFIRE.EXE process observed",exitcode);
 if(preflight){if(exitcode)event("preflight","blocked","Inventory incomplete",exitcode);else if(!guard(proof)){event("preflight","blocked","Missing/incomplete independent host isolation proof",23);exitcode=23;}else if(!netok){event("preflight","blocked","Local network guard failed",22);exitcode=22;}else exitcode=query_optout();}
 WSACleanup();fclose(timeline);return exitcode;
}

/* Explicit XP startup avoids compiler-selected UCRT startup requirements. */
void WINAPI probe_entry(void) {
 int argc=0,i,rc=2; LPWSTR*wide=CommandLineToArgvW(GetCommandLineW(),&argc); char**args=NULL;
 if(wide&&argc>0&&argc<16) {
  args=(char**)malloc((size_t)argc*sizeof(char*));
  if(args){for(i=0;i<argc;i++){int n=WideCharToMultiByte(CP_ACP,0,wide[i],-1,NULL,0,NULL,NULL);args[i]=(char*)malloc((size_t)n);if(!n||!args[i])ExitProcess(3);WideCharToMultiByte(CP_ACP,0,wide[i],-1,args[i],n,NULL,NULL);}rc=probe_main(argc,args);}
 }
 ExitProcess((UINT)rc);
}
/* Zig's COFF link retains this name even without TLS or CRT startup. */
unsigned long _tls_index=0;
