/* XP original Spitfire UI driver: guarded launch, exact safe menus, inventory.
 * No helper UDP traffic. Opt-out ON is bound to the reviewed runtime panel and image.
 * No generic keyboard/click interface. Windows XP SP3 x86. */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <wincrypt.h>
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
static int original_running, original_exact_count, original_foreign;
static DWORD original_pid;
static const WCHAR original_path_w[]=L"C:\\Program Files\\Spectra-Physics\\Spitfire\\Spitfire.exe";
static const char original_path[]="C:\\Program Files\\Spectra-Physics\\Spitfire\\Spitfire.exe";
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
 static WCHAR title[2048];WCHAR cls[256];DWORD pid=0;RECT r={0,0,0,0},client={0,0,0,0};POINT origin={0,0};
 window_text(h,title,2048);GetClassNameW(h,cls,256);GetWindowThreadProcessId(h,&pid);GetWindowRect(h,&r);GetClientRect(h,&client);ClientToScreen(h,&origin);
 fprintf(winfile,"{\"kind\":\"%s\",\"hwnd\":%lu,\"parent_hwnd\":%lu,\"pid\":%lu,\"visible\":%s,\"enabled\":%s,\"control_id\":%d,\"style\":%lu,\"rect\":[%ld,%ld,%ld,%ld],\"class\":",child?"child":"window",(unsigned long)(uintptr_t)h,(unsigned long)(uintptr_t)GetParent(h),(unsigned long)pid,IsWindowVisible(h)?"true":"false",IsWindowEnabled(h)?"true":"false",GetDlgCtrlID(h),(unsigned long)GetWindowLong(h,GWL_STYLE),r.left,r.top,r.right,r.bottom);
 jw(winfile,cls);fputs(",\"text\":",winfile);jw(winfile,title);fprintf(winfile,",\"client_rect\":[%ld,%ld,%ld,%ld],\"client_origin_screen\":[%ld,%ld]}\n",client.left,client.top,client.right,client.bottom,origin.x,origin.y);
}
static BOOL CALLBACK child_cb(HWND h,LPARAM x) { (void)x;if(++window_count>6000)return FALSE;window_record(h,1);return TRUE; }
static BOOL CALLBACK top_cb(HWND h,LPARAM x) { (void)x;if(++window_count>6000)return FALSE;window_record(h,0);menus(h,GetMenu(h),0);EnumChildWindows(h,child_cb,0);return TRUE; }
static int inventory_windows(void) {
 winfile=openout("windows.jsonl","wb");if(!winfile)return 0;
 window_count=0;EnumWindows(top_cb,0);fclose(winfile);winfile=NULL;return 1;
}
static int processes(void) {
 original_running=0;original_exact_count=0;original_foreign=0;original_pid=0;
 HANDLE snap;PROCESSENTRY32W p;FILE*f=openout("processes.jsonl","wb");if(!f)return 0;
 snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);if(snap==INVALID_HANDLE_VALUE){fclose(f);return 0;}
 ZeroMemory(&p,sizeof(p));p.dwSize=sizeof(p);
 if(Process32FirstW(snap,&p))do {
  static WCHAR path[2048];HANDLE h=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,p.th32ProcessID);DWORD error=0;path[0]=0;
  if(h){if(!GetModuleFileNameExW(h,NULL,path,2048))error=GetLastError();CloseHandle(h);}else error=GetLastError();
  if(_wcsicmp(p.szExeFile,L"SPITFIRE.EXE")==0){original_running=1;if(!_wcsicmp(path,original_path_w)){original_exact_count++;original_pid=p.th32ProcessID;}else original_foreign=1;}
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
 static const char *required[]={"schema=spitfire-isolation-v1","vm_host=20255566-p07","vm_network=hostonly","host_ip_forwarding=disabled","host_ics_on_vmnet1=disabled","host_bridge_on_vmnet1=absent","physical_passthrough=absent","simulator_bind=10.19.70.13:1024","simulator_peer=10.19.70.2","simulator_policy=queries-and-empower-optout-on-only","guest_ip=10.19.70.2","authorization=xp-optout-on-and-readonly-navigation"};
 unsigned int found=0,i;char line[1024];FILE*f=path?fopen(path,"rb"):NULL;int stamp=0;FILE*copy;
 if(!f)return 0;copy=openout("host-isolation-proof.txt","wb");
 while(fgets(line,sizeof(line),f)){if(copy)fputs(line,copy);line[strcspn(line,"\r\n")]=0;for(i=0;i<sizeof(required)/sizeof(required[0]);i++)if(!strcmp(line,required[i]))found|=(1u<<i);if(!strncmp(line,"verified_utc=",13)&&strlen(line)>=33)stamp=1;}
 fclose(f);if(copy)fclose(copy);return found==((1u<<(sizeof(required)/sizeof(required[0])))-1)&&stamp;
}
#include "optout_guard.c.inc"
static HWND main_hwnd; static int main_count;
static BOOL CALLBACK main_cb(HWND h,LPARAM x){DWORD p=0;WCHAR title[512],cls[256];RECT r,c;int sw=GetSystemMetrics(SM_CXSCREEN),sh=GetSystemMetrics(SM_CYSCREEN);(void)x;GetWindowThreadProcessId(h,&p);if(p!=original_pid||!IsWindowVisible(h))return TRUE;window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);if(!_wcsicmp(title,L"Spitfire")&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&c.right==895&&c.bottom==550&&r.right>0&&r.bottom>0&&r.left<sw&&r.top<sh){main_hwnd=h;main_count++;}return TRUE;}
static int find_main(void){main_hwnd=NULL;main_count=0;if(original_exact_count!=1||original_foreign)return 0;EnumWindows(main_cb,0);return main_count==1&&IsWindowEnabled(main_hwnd);}
static void normalize_menu(const WCHAR*input,WCHAR*out,int n){int i=0;for(;*input&&i<n-1;input++){if(*input=='&'||*input=='_')continue;if(*input=='\t')break;out[i++]=*input;}while(i&&out[i-1]==' ')i--;out[i]=0;}
static UINT found_command;static int found_commands;static UINT found_state;
static void find_menu(HMENU menu,const WCHAR*label,int depth){int i,n;if(!menu||depth>12)return;n=GetMenuItemCount(menu);if(n>256)return;for(i=0;i<n;i++){WCHAR raw[512],clean[512];HMENU sub;raw[0]=0;GetMenuStringW(menu,i,raw,512,MF_BYPOSITION);normalize_menu(raw,clean,512);sub=GetSubMenu(menu,i);if(!sub&&!_wcsicmp(clean,label)){found_command=GetMenuItemID(menu,i);found_state=GetMenuState(menu,i,MF_BYPOSITION);found_commands++;}if(sub)find_menu(sub,label,depth+1);}}
static int activate_exact(HWND h){DWORD target=GetWindowThreadProcessId(h,NULL),mine=GetCurrentThreadId();int attached=0;if(target!=mine){attached=AttachThreadInput(mine,target,TRUE);if(!attached)return 0;}SetForegroundWindow(h);BringWindowToTop(h);if(attached)AttachThreadInput(mine,target,FALSE);Sleep(180);return GetForegroundWindow()==h;}
static int mouse_click(HWND expected,POINT point,int allow_menu){INPUT input[2];HWND under;DWORD owner=0;POINT current;UINT down,up;if(GetAsyncKeyState(VK_LBUTTON)&0x8000)return 0;if(!SetCursorPos(point.x,point.y))return 0;Sleep(80);GetCursorPos(&current);if(current.x!=point.x||current.y!=point.y)return 0;under=WindowFromPoint(point);GetWindowThreadProcessId(under,&owner);if(owner!=original_pid)return 0;if(!allow_menu&&under!=expected&&!IsChild(expected,under))return 0;ZeroMemory(input,sizeof(input));input[0].type=INPUT_MOUSE;input[0].mi.dwFlags=MOUSEEVENTF_LEFTDOWN;input[1].type=INPUT_MOUSE;input[1].mi.dwFlags=MOUSEEVENTF_LEFTUP;down=SendInput(1,input,sizeof(INPUT));Sleep(120);up=SendInput(1,input+1,sizeof(INPUT));return down==1&&up==1;}
static void interim_inventory(const char*label){char src[MAX_PATH],dst[MAX_PATH];screenshot();inventory_windows();_snprintf(src,sizeof(src),"%s\\desktop.bmp",outdir);_snprintf(dst,sizeof(dst),"%s\\desktop-%s.bmp",outdir,label);MoveFileA(src,dst);_snprintf(src,sizeof(src),"%s\\windows.jsonl",outdir);_snprintf(dst,sizeof(dst),"%s\\windows-%s.jsonl",outdir,label);MoveFileA(src,dst);}
static POINT popup_origin,popup_item;static RECT popup_expected;static int popup_matches;
static BOOL CALLBACK popup_cb(HWND h,LPARAM x){DWORD pid=0;RECT r;WCHAR cls[128];(void)x;GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||!IsWindowVisible(h))return TRUE;GetClassNameW(h,cls,128);if(_wcsicmp(cls,L"CVIRTLVMenuWnd4194304"))return TRUE;GetWindowRect(h,&r);if(r.left>=popup_origin.x+popup_expected.left-5&&r.left<=popup_origin.x+popup_expected.left+5&&r.top>=popup_origin.y+popup_expected.top-4&&r.top<=popup_origin.y+popup_expected.top+4&&r.right>=popup_origin.x+popup_expected.right-7&&r.right<=popup_origin.x+popup_expected.right+7&&r.bottom>=popup_origin.y+popup_expected.bottom-7&&r.bottom<=popup_origin.y+popup_expected.bottom+7&&PtInRect(&r,popup_item))popup_matches++;return TRUE;}
static int observed_popup(POINT origin,POINT item,RECT expected){popup_origin=origin;popup_item=item;popup_expected=expected;popup_matches=0;EnumWindows(popup_cb,0);return popup_matches==1;}
static int custom_menu(const WCHAR*label){POINT menu={52,9},item={107,0},origin={0,0};RECT popup={35,20,228,88};int optout,level;if(!_wcsicmp(label,L"Empower Setup"))item.y=28;else if(!_wcsicmp(label,L"Active Faults"))item.y=44;else if(!_wcsicmp(label,L"Timing and High Voltage"))item.y=60;else if(!_wcsicmp(label,L"Temperature Control"))item.y=76;else if(!_wcsicmp(label,L"About")){menu.x=90;item.y=28;popup.left=75;popup.right=161;popup.bottom=40;}else if(!_wcsicmp(label,L"Exit")){menu.x=15;item.x=35;item.y=28;popup.left=3;popup.right=77;popup.bottom=40;}else {event("menu","blocked","Custom menu label not allowlisted",32);return 32;}
 if(!original_state("original-state-menu-guard.json",&optout,&level)){event("menu","blocked","Original identity/state read guard failed",40);return 40;}
 if(!find_main()||!activate_exact(main_hwnd)){event("menu","blocked","Verified main panel cannot be foregrounded",41);return 41;}ClientToScreen(main_hwnd,&origin);menu.x+=origin.x;menu.y+=origin.y;item.x+=origin.x;item.y+=origin.y;
 if(!mouse_click(main_hwnd,menu,0)){event("menu","blocked","Verified menu point is obscured or input failed",42);return 42;}Sleep(300);interim_inventory("menu-open");
 if(!observed_popup(origin,item,popup)){event("menu","blocked","Expected original-process popup geometry not observed; no item click",43);return 43;}
 if(!mouse_click(main_hwnd,item,1)){event("menu","blocked","Menu item point lost original-process ownership",44);return 44;}event("menu","sent","Observed CVI popup item clicked; allowed menu action",item.y-origin.y);Sleep(1700);return 0;}
/* Reviewed CVI titlebar/system Close semantics: original panel6 ATTR_CLOSE_CTRL=2,
 * control2 BTN_QUIT -> QuitProgram -> QuitUserInterface only, zero UDP commands.
 * Only reached for Exit when the custom File popup guard returned43 without
 * clicking any menu item. Not a generic process termination interface. */
static int titlebar_exit_fallback(void){int optout,level;HANDLE process;DWORD waited;WCHAR path[MAX_PATH];
 event("exit","menu_unavailable","File popup guard failed43 before any item click; trying reviewed main close-control path",43);
 if(!original_state("original-state-titlebar-exit-guard.json",&optout,&level)||!find_main()||!activate_exact(main_hwnd)){event("exit","blocked","Exact original image and visible enabled main panel required for titlebar fallback",67);return 67;}
 process=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);if(!process){event("exit","blocked","Cannot open identified original process for bounded exit wait",68);return 68;}
 path[0]=0;if(!GetModuleFileNameExW(process,NULL,path,MAX_PATH)||_wcsicmp(path,original_path_w)){CloseHandle(process);event("exit","blocked","Original process identity changed before titlebar fallback",69);return 69;}
 interim_inventory("exit-titlebar-target");
 event("exit","titlebar_fallback_begin","One WM_SYSCOMMAND SC_CLOSE to reviewed main; CVI close_ctrl2 invokes QuitProgram/QuitUserInterface; no ESC or termination",0);
 if(!PostMessageW(main_hwnd,WM_SYSCOMMAND,SC_CLOSE,0)){CloseHandle(process);event("exit","failed","Reviewed titlebar close message rejected; no retry",70);return 70;}
 waited=WaitForSingleObject(process,7000);CloseHandle(process);
 if(waited!=WAIT_OBJECT_0){event("exit","unconfirmed","Original did not exit within7s after one reviewed titlebar close; no termination or further input",71);return 71;}
 event("exit","titlebar_fallback_confirmed","Identified original process exited through reviewed GUI close-control path",0);return 0;
}
static int invoke_menu(const WCHAR*label){HMENU menu;if(!find_main()){event("menu","blocked","Exact original process and visible enabled Spitfire main window required",31);return 31;}menu=GetMenu(main_hwnd);if(!menu){int result=custom_menu(label);if(result==43&&!_wcsicmp(label,L"Exit"))return titlebar_exit_fallback();return result;}found_commands=0;found_command=0;find_menu(menu,label,0);if(found_commands!=1||found_command==(UINT)-1||(found_state&(MF_DISABLED|MF_GRAYED))){event("menu","blocked","Exact allowed menu not uniquely enabled",33);return 33;}if(!PostMessageW(main_hwnd,WM_COMMAND,MAKEWPARAM(found_command,0),0)){event("menu","failed","PostMessage WM_COMMAND rejected",34);return 34;}event("menu","sent","Invoked actual enabled HMENU command matched by allowlisted label",(int)found_command);Sleep(1700);return 0;}
static int launch_original(void){STARTUPINFOA si;PROCESS_INFORMATION pi;char command[MAX_PATH+4];FILE*f;WIN32_FILE_ATTRIBUTE_DATA meta;char hash[65];DWORD hash_error=0;if(original_running){event("launch","blocked","Original already running; no duplicate process",35);return 35;}if(!GetFileAttributesExA(original_path,GetFileExInfoStandard,&meta)||meta.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY){event("launch","blocked","Original EXE missing at locked path",36);return 36;}if(!original_sha256(hash,&hash_error)){event("launch","blocked","Locked original image does not match reviewed SHA256",60);return 60;}f=openout("original-file-launch-guard.json","wb");if(f){fputs("{\"sha256\":",f);js(f,hash);fputs(",\"matches_reviewed_image\":true}\n",f);fclose(f);}ZeroMemory(&si,sizeof(si));si.cb=sizeof(si);ZeroMemory(&pi,sizeof(pi));_snprintf(command,sizeof(command),"\"%s\"",original_path);if(!CreateProcessA(original_path,command,NULL,NULL,FALSE,0,NULL,"C:\\Program Files\\Spectra-Physics\\Spitfire",&si,&pi)){event("launch","failed","CreateProcess failed",(int)GetLastError());return 37;}f=openout("launched-original.json","wb");if(f){fprintf(f,"{\"pid\":%lu,\"path\":",(unsigned long)pi.dwProcessId);js(f,original_path);fprintf(f,",\"file_bytes\":%lu,\"file_time_high\":%lu,\"file_time_low\":%lu,\"commandline_parameters\":false,\"original_binary_modified\":false}\n",(unsigned long)meta.nFileSizeLow,(unsigned long)meta.ftLastWriteTime.dwHighDateTime,(unsigned long)meta.ftLastWriteTime.dwLowDateTime);fclose(f);}event("launch","started","Original vendor EXE launched unmodified; simulator must reject forbidden writes",(int)pi.dwProcessId);CloseHandle(pi.hThread);WaitForInputIdle(pi.hProcess,5000);CloseHandle(pi.hProcess);Sleep(3000);return 0;}
static int regensvc(void){DWORD thread,mine;GUITHREADINFO gui;int attached=0,i,optout,level;const char*word="regensvc";if(!original_state("original-state-service-guard.json",&optout,&level)){event("regensvc","blocked","Original identity/state guard failed",40);return 40;}if(!find_main()){event("regensvc","blocked","Exact original main window required",31);return 31;}thread=GetWindowThreadProcessId(main_hwnd,NULL);mine=GetCurrentThreadId();if(thread!=mine){attached=AttachThreadInput(mine,thread,TRUE);if(!attached)return 38;}SetForegroundWindow(main_hwnd);SetFocus(main_hwnd);ZeroMemory(&gui,sizeof(gui));gui.cbSize=sizeof(gui);if(!GetGUIThreadInfo(thread,&gui)||GetForegroundWindow()!=main_hwnd||gui.hwndFocus!=main_hwnd){if(attached)AttachThreadInput(mine,thread,FALSE);event("regensvc","blocked","Main panel could not receive focus; no keys sent",38);return 38;}for(i=0;word[i];i++){INPUT k[2];WORD vk=(WORD)(word[i]-'a'+'A');ZeroMemory(k,sizeof(k));k[0].type=INPUT_KEYBOARD;k[0].ki.wVk=vk;k[1]=k[0];k[1].ki.dwFlags=KEYEVENTF_KEYUP;if(SendInput(2,k,sizeof(INPUT))!=2){if(attached)AttachThreadInput(mine,thread,FALSE);event("regensvc","failed","Keyboard input incomplete; no recovery keys sent",39);return 39;}Sleep(80);}if(attached)AttachThreadInput(mine,thread,FALSE);event("regensvc","sent","Typed fixed service display sequence into focused main panel",0);Sleep(1300);return 0;}
static HWND temperature_hwnd;static int temperature_count;
static BOOL CALLBACK temperature_cb(HWND h,LPARAM x){DWORD pid=0;WCHAR title[512],cls[256];RECT r,c;(void)x;GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||!IsWindowVisible(h)||!IsWindowEnabled(h))return TRUE;window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);if(!_wcsicmp(title,L"Temperature Control")&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&c.left==0&&c.top==0&&c.right==480&&c.bottom==480&&r.left>=0&&r.top>=0&&r.right<=GetSystemMetrics(SM_CXSCREEN)&&r.bottom<=GetSystemMetrics(SM_CYSCREEN)){temperature_hwnd=h;temperature_count++;}return TRUE;}
static int optout_on(void){int optout,level;POINT point={255,443};
 if(!original_state("original-state-optout-guard.json",&optout,&level)){event("optout_on","blocked","Exact original image/base and readable known globals are required",50);return 50;}
 if(optout==1){event("optout_on","already_on","Empower Opt-out already ON; no input sent",0);return 0;}
 if(optout!=0||level!=1){event("optout_on","blocked","Requires verified OFF state and regensvc access level 1",51);return 51;}
 temperature_hwnd=NULL;temperature_count=0;EnumWindows(temperature_cb,0);if(temperature_count!=1){event("optout_on","blocked","Exactly one observed original Temperature Control 480x480 panel required",52);return 52;}
 if(!activate_exact(temperature_hwnd)){event("optout_on","blocked","Verified Temperature Control panel cannot be foregrounded",53);return 53;}
 interim_inventory("optout-target");
 if(!original_state("original-state-optout-immediate.json",&optout,&level)||optout!=0||level!=1){event("optout_on","blocked","State changed before input; no click sent",54);return 54;}
 if(!ClientToScreen(temperature_hwnd,&point)||GetForegroundWindow()!=temperature_hwnd){event("optout_on","blocked","Target panel lost foreground or coordinate mapping failed",55);return 55;}
 event("optout_on","click_begin","One authorized click: reviewed Empower Opt-out switch ON side client (255,443); no retries",0);
 if(!mouse_click(temperature_hwnd,point,0)){event("optout_on","failed","Reviewed switch input failed; no retry attempted",56);return 56;}
 Sleep(250);interim_inventory("optout-clicked");Sleep(1750);
 if(!original_state("original-state-optout-after.json",&optout,&level)||optout!=1){event("optout_on","unconfirmed","Single click sent; ON global not confirmed; no retry attempted",57);return 57;}
 event("optout_on","confirmed","Original application read-only emp_optout global changed from 0 to 1 after one UI click; controller reply is simulated",0);return 0;
}
/* Runtime-reviewed modal connection warning only. The historical `close` queue
 * verb is retained for compatibility; this sends its OK retry button, not WM_CLOSE. */
static HWND retry_warning_hwnd;static int retry_warning_count;
static BOOL CALLBACK retry_warning_cb(HWND h,LPARAM x){DWORD pid=0;WCHAR title[512],cls[256];RECT r,c;(void)x;GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||!IsWindowVisible(h)||!IsWindowEnabled(h))return TRUE;window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);if(!_wcsicmp(title,L"Warning")&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&c.left==0&&c.top==0&&c.right==308&&c.bottom==85&&r.left>=0&&r.top>=0&&r.right<=GetSystemMetrics(SM_CXSCREEN)&&r.bottom<=GetSystemMetrics(SM_CYSCREEN)){retry_warning_hwnd=h;retry_warning_count++;}return TRUE;}
static int retry_connection_warning(void){int optout,level;POINT point={154,58};
 if(!original_state("original-state-retry-guard.json",&optout,&level)||optout!=1){event("close","blocked","Connection retry requires exact original image/state and Empower Opt-out already ON",61);return 61;}
 retry_warning_hwnd=NULL;retry_warning_count=0;EnumWindows(retry_warning_cb,0);
 if(retry_warning_count!=1){event("close","blocked","Exactly one reviewed Warning CVI panel with client308x85 required; no generic close allowed",62);return 62;}
 if(!activate_exact(retry_warning_hwnd)){event("close","blocked","Reviewed connection warning cannot be foregrounded",63);return 63;}
 interim_inventory("connection-retry-target");
 if(!original_state("original-state-retry-immediate.json",&optout,&level)||optout!=1||!ClientToScreen(retry_warning_hwnd,&point)||GetForegroundWindow()!=retry_warning_hwnd){event("close","blocked","Original ON state or warning foreground lost before retry",64);return 64;}
 event("close","retry_begin","One reviewed connection-warning OK click at client(154,58), 120ms hold; no fault reset or generic close",0);
 if(!mouse_click(retry_warning_hwnd,point,0)){event("close","failed","Connection-warning OK input failed; no retry loop",65);return 65;}
 Sleep(350);interim_inventory("connection-retry-clicked");Sleep(1650);
 retry_warning_hwnd=NULL;retry_warning_count=0;EnumWindows(retry_warning_cb,0);
 if(retry_warning_count){event("close","unconfirmed","Connection warning still visible after one OK click; no further input sent",66);return 66;}
 event("close","sent","Reviewed connection warning no longer visible; verify actual simulator traffic separately",0);return 0;
}
static int driver_main(int argc,char**argv){WSADATA wsa;int rc=0,netok,inventory,optout=-1,access=-1;const WCHAR*label=NULL;const char*mode;FILE*f;char t[40],path[MAX_PATH];
 if(argc<3||argc>4)return 2;mode=argv[1];inventory=!strcmp(mode,"inventory");
 if(!inventory&&strcmp(mode,"launch")&&strcmp(mode,"regensvc")&&strcmp(mode,"optout_on")&&strcmp(mode,"close")){if(!strcmp(mode,"about"))label=L"About";else if(!strcmp(mode,"temperature"))label=L"Temperature Control";else if(!strcmp(mode,"timing"))label=L"Timing and High Voltage";else if(!strcmp(mode,"faults"))label=L"Active Faults";else if(!strcmp(mode,"setup"))label=L"Empower Setup";else if(!strcmp(mode,"exit"))label=L"Exit";else return 2;}
 if(!inventory&&argc!=4)return 2;if(strlen(argv[2])>MAX_PATH-64)return 2;strcpy(outdir,argv[2]);if(!CreateDirectoryA(outdir,NULL))return 3;timeline=openout("timeline.jsonl","wb");if(!timeline)return 3;
 event(mode,"begin","Guest native UI driver; no helper UDP generation",0);if(WSAStartup(MAKEWORD(2,2),&wsa)){fclose(timeline);return 4;}
 if(!processes()||!inventory_windows()||!screenshot()){event(mode,"blocked","Initial inventory incomplete",4);rc=4;goto done;}
 _snprintf(path,sizeof(path),"%s\\desktop.bmp",outdir);{char dest[MAX_PATH];_snprintf(dest,sizeof(dest),"%s\\desktop-before.bmp",outdir);MoveFileA(path,dest);_snprintf(path,sizeof(path),"%s\\windows.jsonl",outdir);_snprintf(dest,sizeof(dest),"%s\\windows-before.jsonl",outdir);MoveFileA(path,dest);_snprintf(path,sizeof(path),"%s\\processes.jsonl",outdir);_snprintf(dest,sizeof(dest),"%s\\processes-before.jsonl",outdir);MoveFileA(path,dest);}
 original_state("original-state-before.json",&optout,&access);
 netok=network_inventory();event("local_network_check",netok?"end":"blocked",netok?"One expected IPv4 adapter; no gateway/default route; direct simulator route":"Local network guard failed",netok?0:22);
 if(!inventory){if(!netok){rc=22;goto done;}if(!guard(argv[3])){event(mode,"blocked","Independent host proof missing or incomplete",23);rc=23;goto done;}if(!strcmp(mode,"launch"))rc=launch_original();else if(!strcmp(mode,"regensvc"))rc=regensvc();else if(!strcmp(mode,"optout_on"))rc=optout_on();else if(!strcmp(mode,"close"))rc=retry_connection_warning();else rc=invoke_menu(label);}
 done:processes();inventory_windows();screenshot();original_state("original-state.json",&optout,&access);utc(t,sizeof(t));f=openout("result.json","wb");if(f){fputs("{\"utc_guest_clock\":",f);js(f,t);fputs(",\"mode\":",f);js(f,mode);fprintf(f,",\"exit_code\":%d,\"original_pid\":%lu,\"original_exact_count\":%d,\"foreign_original_name\":%s,\"helper_udp_generated\":false}\n",rc,(unsigned long)original_pid,original_exact_count,original_foreign?"true":"false");fclose(f);}event(mode,rc?"blocked_or_failed":"end","Action finished; before/after screenshot and inventory retained",rc);WSACleanup();fclose(timeline);return rc;
}
void WINAPI probe_entry(void){int argc=0,i,rc=2;LPWSTR*wide=CommandLineToArgvW(GetCommandLineW(),&argc);char**args=NULL;if(wide&&argc>0&&argc<16){args=(char**)malloc((size_t)argc*sizeof(char*));if(args){for(i=0;i<argc;i++){int n=WideCharToMultiByte(CP_ACP,0,wide[i],-1,NULL,0,NULL,NULL);args[i]=(char*)malloc((size_t)n);if(!n||!args[i])ExitProcess(3);WideCharToMultiByte(CP_ACP,0,wide[i],-1,args[i],n,NULL,NULL);}rc=driver_main(argc,args);}}ExitProcess((UINT)rc);}
unsigned long _tls_index=0;
