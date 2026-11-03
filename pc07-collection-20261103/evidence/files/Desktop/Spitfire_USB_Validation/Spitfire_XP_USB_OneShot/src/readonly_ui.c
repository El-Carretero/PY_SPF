/* XP physical-PC passive-test UI controller. Attach only to reviewed running original.
 * Fixed display/navigation actions only. No sockets, process launches, device settings,
 * warning acknowledgement, main close, Escape, arbitrary keys or click coordinates. */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
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
static const char *proof_path, *stop_path;
static int initial_access=-1, current_access=-1, current_optout=-1, hold_thread=-1;
static int resource_ok, runtime_ok, original_state_ok;
static DWORD proof_tick;
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
static BOOL CALLBACK top_cb(HWND h,LPARAM x) { DWORD pid=0;(void)x;GetWindowThreadProcessId(h,&pid);if(pid!=original_pid&&h!=GetForegroundWindow())return TRUE;if(++window_count>6000)return FALSE;window_record(h,0);menus(h,GetMenu(h),0);EnumChildWindows(h,child_cb,0);return TRUE; }
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

#ifndef CALG_SHA_256
#define CALG_SHA_256 0x0000800c
#endif
static const char exe_sha[]="8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b";
static const char uir_sha[]="1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b";
static const char cvi_sha[]="d4151c53a2ecee4431ba88cd90d88db575f8ad18a6e48484501ff10a83c0db6d";
static const WCHAR uir_path[]=L"C:\\Program Files\\Spectra-Physics\\Spitfire\\SPITFIRE.UIR";
static char actual_exe[65],actual_uir[65],actual_cvi[65];
static WCHAR loaded_cvi[MAX_PATH];
static int hash_file(const WCHAR *path,char hex[65],const char *expected,DWORD *error) {
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;HANDLE file=INVALID_HANDLE_VALUE;
 static BYTE buffer[8192];BYTE digest[32];DWORD got=0,size=32;int i,ok=0;
 const char *digits="0123456789abcdef";hex[0]=0;*error=0;
 if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&
    !CryptAcquireContextW(&provider,NULL,L"Microsoft Enhanced RSA and AES Cryptographic Provider (Prototype)",PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&
    !CryptAcquireContextW(&provider,NULL,L"Microsoft Enhanced RSA and AES Cryptographic Provider",PROV_RSA_AES,CRYPT_VERIFYCONTEXT)){*error=GetLastError();goto done;}
 if(!CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)){*error=GetLastError();goto done;}
 file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
 if(file==INVALID_HANDLE_VALUE){*error=GetLastError();goto done;}
 for(;;){if(!ReadFile(file,buffer,sizeof(buffer),&got,NULL)){*error=GetLastError();goto done;}if(!got)break;if(!CryptHashData(hash,buffer,got,0)){*error=GetLastError();goto done;}}
 if(!CryptGetHashParam(hash,HP_HASHVAL,digest,&size,0)||size!=32){*error=GetLastError();goto done;}
 for(i=0;i<32;i++){hex[2*i]=digits[digest[i]>>4];hex[2*i+1]=digits[digest[i]&15];}hex[64]=0;ok=!strcmp(hex,expected);
 done:if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);return ok;
}
static HWND main_hwnd;static int main_count,warning_count;
static BOOL CALLBACK main_cb(HWND h,LPARAM x) {
 DWORD pid=0;WCHAR title[512],cls[256];RECT r,c;(void)x;
 GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||!IsWindowVisible(h))return TRUE;
 window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);
 if(!_wcsicmp(title,L"Warning")||!_wcsicmp(cls,L"#32770"))warning_count++;
 if(!_wcsicmp(title,L"Spitfire")&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&
    c.left==0&&c.top==0&&c.right==895&&c.bottom==550&&r.left>=0&&r.top>=0&&
    r.right<=GetSystemMetrics(SM_CXSCREEN)&&r.bottom<=GetSystemMetrics(SM_CYSCREEN)){
  main_hwnd=h;main_count++;
 }
 return TRUE;
}
static int find_main(void) {
 main_hwnd=NULL;main_count=warning_count=0;
 if(original_exact_count!=1||original_foreign)return 0;
 EnumWindows(main_cb,0);return main_count==1&&IsWindowEnabled(main_hwnd)&&warning_count==0;
}
static int read_int(HANDLE process,uintptr_t address,int *value) {
 SIZE_T bytes=0;return ReadProcessMemory(process,(LPCVOID)address,value,sizeof(*value),&bytes)&&bytes==sizeof(*value);
}
static int original_state(const char *leaf,int *optout,int *access) {
 DWORD error=0,cvi_error=0,uir_error=0;HANDLE process=NULL,snapshot=INVALID_HANDLE_VALUE;
 MODULEENTRY32W module;int hash_ok=0,base_ok=0,ok=0,first=1,cvi_count=0,main_ok=0;FILE *f;
 actual_exe[0]=actual_uir[0]=actual_cvi[0]=0;loaded_cvi[0]=0;
 *optout=*access=hold_thread=-1;resource_ok=runtime_ok=0;
 if(original_exact_count!=1||original_foreign||!original_pid){error=ERROR_NOT_FOUND;goto done;}
 hash_ok=hash_file(original_path_w,actual_exe,exe_sha,&error);if(!hash_ok)goto done;
 resource_ok=hash_file(uir_path,actual_uir,uir_sha,&uir_error);
 snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,original_pid);
 if(snapshot==INVALID_HANDLE_VALUE){error=GetLastError();goto done;}
 ZeroMemory(&module,sizeof(module));module.dwSize=sizeof(module);
 if(!Module32FirstW(snapshot,&module)){error=GetLastError();goto done;}
 do {
  if(first){base_ok=!_wcsicmp(module.szExePath,original_path_w)&&(uintptr_t)module.modBaseAddr==0x400000u;first=0;}
  if(!_wcsicmp(module.szModule,L"cvirte.dll")){cvi_count++;lstrcpynW(loaded_cvi,module.szExePath,MAX_PATH);}
 }while(Module32NextW(snapshot,&module));
 if(!base_ok){error=ERROR_INVALID_ADDRESS;goto done;}
 if(cvi_count==1)runtime_ok=hash_file(loaded_cvi,actual_cvi,cvi_sha,&cvi_error);
 process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);
 if(!process){error=GetLastError();goto done;}
 if(!read_int(process,0x4141D0u,optout)||!read_int(process,0x416DECu,access)||!read_int(process,0x414A9Cu,&hold_thread)){error=GetLastError();goto done;}
 ok=(*optout==0||*optout==1)&&*access>=0&&*access<=3&&(hold_thread==0||hold_thread==1);
 done:
 if(process)CloseHandle(process);if(snapshot!=INVALID_HANDLE_VALUE)CloseHandle(snapshot);
 main_ok=find_main();original_state_ok=ok;current_access=*access;current_optout=*optout;
 f=openout(leaf,"wb");if(f){
  fprintf(f,"{\"pid\":%lu,\"read_only\":true,\"expected_sha256\":",(unsigned long)original_pid);js(f,exe_sha);
  fputs(",\"actual_sha256\":",f);js(f,actual_exe);
  fputs(",\"uir_sha256\":",f);js(f,actual_uir);fputs(",\"cvirte_sha256\":",f);js(f,actual_cvi);fputs(",\"cvirte_path\":",f);jw(f,loaded_cvi);
  fprintf(f,",\"hash_matches\":%s,\"base_matches_0x400000\":%s,\"resource_matches\":%s,\"runtime_matches\":%s,\"state_valid\":%s,\"emp_optout\":%d,\"gAccessLevel\":%d,\"hold_thread\":%d,\"main_hwnd\":%lu,\"main_matches\":%s,\"blocking_warning_count\":%d,\"win32_error\":%lu,\"uir_error\":%lu,\"cvi_error\":%lu}\n",
   hash_ok?"true":"false",base_ok?"true":"false",resource_ok?"true":"false",runtime_ok?"true":"false",ok?"true":"false",*optout,*access,hold_thread,(unsigned long)(uintptr_t)main_hwnd,main_ok?"true":"false",warning_count,(unsigned long)error,(unsigned long)uir_error,(unsigned long)cvi_error);fclose(f);
 }
 return ok;
}
static int cancelled(void) {
 return (stop_path&&GetFileAttributesA(stop_path)!=INVALID_FILE_ATTRIBUTES)||(GetAsyncKeyState(VK_F12)&0x8000);
}
static int wait_cancel(DWORD ms) {
 DWORD start=GetTickCount();do{if(cancelled())return 0;Sleep(50);}while((DWORD)(GetTickCount()-start)<ms);return 1;
}
static int decimal(const char *s,DWORD *out) {
 DWORD v=0;if(!*s)return 0;
 for(;*s;s++){DWORD d=(DWORD)(*s-'0');if(d>9||v>429496729u||(v==429496729u&&d>5))return 0;v=v*10+d;}*out=v;return 1;
}
/* Root orchestrator writes this proof only after reading live passive capture status.
 * This is a freshness/coordination guard, not a cryptographic authorization token. */
static int capture_proof_once(void) {
 static const char *keys[]={"schema=","ui_ready=","write_commands=","observed_pairs=","updated_tick=","original_pid=","initial_access="};
 char line[512];DWORD values[7]={0};unsigned seen=0;int i,ok=1;FILE *f,*copy;
 f=proof_path?fopen(proof_path,"rb"):NULL;if(!f)return -1;copy=openout("capture-proof.txt","wb");
 while(fgets(line,sizeof(line),f)){
  if(copy)fputs(line,copy);line[strcspn(line,"\r\n")]=0;if(!line[0])continue;
  for(i=0;i<7;i++)if(!strncmp(line,keys[i],strlen(keys[i])))break;
  if(i==7||(seen&(1u<<i))){ok=0;break;}seen|=1u<<i;
  if(i==0){if(strcmp(line+strlen(keys[i]),"spitfire-passive-v1"))ok=0;}
  else if(!decimal(line+strlen(keys[i]),&values[i]))ok=0;
 }
 fclose(f);if(copy)fclose(copy);
 if(!ok)return 0;if(seen!=127)return -1;
 if(values[1]!=1||values[2]!=0||values[3]!=1||values[5]!=original_pid||values[6]>1||(DWORD)(GetTickCount()-values[4])>5000)return 0;
 proof_tick=values[4];initial_access=(int)values[6];return 1;
}
static int capture_proof(void) {
 int i,rc;
 /* FSO replacement can briefly remove the path. Retry missing/incomplete files
  * only; never reuse a previously accepted proof or relax its freshness limit. */
 for(i=0;i<3;i++){
  if(cancelled())return 0;rc=capture_proof_once();if(rc>=0)return rc;
  if(i<2)Sleep(20);
 }
 return 0;
}
static int action_guard(const char *action) {
 int optout,access;
 if(cancelled()){event(action,"cancelled","STOP file or F12; no further UI input",80);return 0;}
 if(!capture_proof()){event(action,"blocked","Fresh passive bidirectional capture proof missing or invalid",81);return 0;}
 if(!original_state("original-state-immediate.json",&optout,&access)||!resource_ok||!runtime_ok||optout!=1||access<0||access>1||hold_thread!=0||!find_main()){
  event(action,"blocked","Requires original image/resource, Opt-out ON, user/service, no warning, connected main panel",82);return 0;
 }
 return 1;
}
static void snapshot(const char *label) {
 char src[MAX_PATH],dst[MAX_PATH];
 screenshot();inventory_windows();
 _snprintf(src,sizeof(src),"%s\\desktop.bmp",outdir);_snprintf(dst,sizeof(dst),"%s\\desktop-%s.bmp",outdir,label);MoveFileA(src,dst);
 _snprintf(src,sizeof(src),"%s\\windows.jsonl",outdir);_snprintf(dst,sizeof(dst),"%s\\windows-%s.jsonl",outdir,label);MoveFileA(src,dst);
}
static int activate_exact(HWND h) {
 DWORD target=GetWindowThreadProcessId(h,NULL),mine=GetCurrentThreadId();int attached=0;
 if(target!=mine){attached=AttachThreadInput(mine,target,TRUE);if(!attached)return 0;}
 SetForegroundWindow(h);BringWindowToTop(h);if(attached)AttachThreadInput(mine,target,FALSE);
 return wait_cancel(180)&&GetForegroundWindow()==h;
}
static int modifiers_down(void) {
 return (GetAsyncKeyState(VK_SHIFT)&0x8000)||(GetAsyncKeyState(VK_CONTROL)&0x8000)||
        (GetAsyncKeyState(VK_MENU)&0x8000)||(GetAsyncKeyState(VK_LWIN)&0x8000)||
        (GetAsyncKeyState(VK_RWIN)&0x8000)||(GetAsyncKeyState(VK_LBUTTON)&0x8000)||
        (GetAsyncKeyState(VK_RBUTTON)&0x8000);
}
static POINT action_main_origin;
static int menu_target_unchanged(HWND expected,POINT point,int allow_menu);
static int mouse_click(HWND expected,POINT point,int allow_menu) {
 INPUT input[2];HWND under;DWORD owner=0;POINT current;UINT down,up;
 if(cancelled()||modifiers_down()||GetForegroundWindow()!=main_hwnd)return 0;
 if(!SetCursorPos(point.x,point.y)||!wait_cancel(80))return 0;GetCursorPos(&current);
 if(current.x!=point.x||current.y!=point.y)return 0;
 under=WindowFromPoint(point);GetWindowThreadProcessId(under,&owner);
 if(owner!=original_pid||(!allow_menu&&under!=expected&&!IsChild(expected,under))||cancelled()||!capture_proof())return 0;
 /* No delay or file hashing between this final geometry/popup check and input. */
 if(!menu_target_unchanged(expected,point,allow_menu))return 0;
 ZeroMemory(input,sizeof(input));input[0].type=INPUT_MOUSE;input[0].mi.dwFlags=MOUSEEVENTF_LEFTDOWN;
 input[1].type=INPUT_MOUSE;input[1].mi.dwFlags=MOUSEEVENTF_LEFTUP;
 down=SendInput(1,input,sizeof(INPUT));Sleep(120);
 /* Always release only our own held button, even when cancellation arrives. */
 up=SendInput(1,input+1,sizeof(INPUT));if(up!=1)up=SendInput(1,input+1,sizeof(INPUT));return down==1&&up==1;
}
typedef struct {const char *mode;const WCHAR *menu,*title;int width0,height0,width1,height1,item_y,close_control;} Panel;
static const Panel panels[]={
 {"temperature",L"Temperature Control",L"Temperature Control",480,250,480,480,76,6},
 {"timing",L"Timing and High Voltage",L"Timing and High Voltage",390,446,750,446,60,21},
 {"faults",L"Active Faults",L"Active Faults",720,580,720,580,44,33},
 {"setup",L"Empower Setup",L"Empower Setup",544,250,544,480,28,12},
 {"about",L"About",L"Help",500,277,500,277,28,9}
};
static const Panel *find_panel_spec;static HWND panel_hwnd;static int panel_count;
static BOOL CALLBACK panel_cb(HWND h,LPARAM x) {
 DWORD pid=0;WCHAR title[512],cls[256];RECT r,c;int level=current_access;(void)x;
 GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||!IsWindowVisible(h)||!IsWindowEnabled(h))return TRUE;
 window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);
 if(!_wcsicmp(title,find_panel_spec->title)&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&
    c.left==0&&c.top==0&&c.right==(level?find_panel_spec->width1:find_panel_spec->width0)&&
    c.bottom==(level?find_panel_spec->height1:find_panel_spec->height0)&&r.left>=0&&r.top>=0&&
    r.right<=GetSystemMetrics(SM_CXSCREEN)&&r.bottom<=GetSystemMetrics(SM_CYSCREEN)){panel_hwnd=h;panel_count++;}
 return TRUE;
}
static int find_panel(const Panel *p) {find_panel_spec=p;panel_hwnd=NULL;panel_count=0;EnumWindows(panel_cb,0);return panel_count==1;}
static POINT popup_origin,popup_item;static RECT popup_expected;static int popup_matches;static HWND popup_hwnd;
static BOOL CALLBACK popup_cb(HWND h,LPARAM x) {
 DWORD pid=0;RECT r;WCHAR cls[128];(void)x;GetWindowThreadProcessId(h,&pid);
 if(pid!=original_pid||!IsWindowVisible(h))return TRUE;
 GetClassNameW(h,cls,128);if(_wcsicmp(cls,L"CVIRTLVMenuWnd4194304"))return TRUE;
 GetWindowRect(h,&r);
 if(r.left>=popup_origin.x+popup_expected.left-5&&r.left<=popup_origin.x+popup_expected.left+5&&
    r.top>=popup_origin.y+popup_expected.top-4&&r.top<=popup_origin.y+popup_expected.top+4&&
    r.right>=popup_origin.x+popup_expected.right-7&&r.right<=popup_origin.x+popup_expected.right+7&&
    r.bottom>=popup_origin.y+popup_expected.bottom-7&&r.bottom<=popup_origin.y+popup_expected.bottom+7&&PtInRect(&r,popup_item)){popup_matches++;popup_hwnd=h;}
 return TRUE;
}
static int observed_popup(POINT origin,POINT item,RECT expected) {
 popup_origin=origin;popup_item=item;popup_expected=expected;popup_matches=0;popup_hwnd=NULL;EnumWindows(popup_cb,0);return popup_matches==1;
}
static int menu_target_unchanged(HWND expected,POINT point,int allow_menu) {
 DWORD pid=0;RECT client;POINT origin={0,0};WCHAR title[512],cls[256];HWND under;
 GetWindowThreadProcessId(expected,&pid);
 if(expected!=main_hwnd||pid!=original_pid||!IsWindowVisible(expected)||!IsWindowEnabled(expected)||GetForegroundWindow()!=expected)return 0;
 window_text(expected,title,512);GetClassNameW(expected,cls,256);
 if(_wcsicmp(title,L"Spitfire")||_wcsicmp(cls,L"CVIRTLVDChild4194304")||!GetClientRect(expected,&client)||client.left!=0||client.top!=0||client.right!=895||client.bottom!=550)return 0;
 if(!ClientToScreen(expected,&origin)||origin.x!=action_main_origin.x||origin.y!=action_main_origin.y)return 0;
 if(allow_menu&&!observed_popup(origin,point,popup_expected))return 0;
 under=WindowFromPoint(point);
 /* The reviewed CVI popup is disabled to Win32 hit testing, which can return
  * its underlying main window. Other same-PID auxiliary windows are rejected. */
 if(under!=expected&&!IsChild(expected,under)&&(!allow_menu||under!=popup_hwnd))return 0;
 return !cancelled()&&!modifiers_down();
}
static int show_panel(const Panel *p) {
 POINT menu={52,9},item={107,0},origin={0,0};RECT popup={35,20,228,88};int already_visible;HWND target;
 if(!action_guard(p->mode))return 82;
 already_visible=find_panel(p);if(panel_count>1)return 83;
 if(!activate_exact(main_hwnd)){event(p->mode,"blocked","Exact main panel cannot be foregrounded",84);return 84;}
 item.y=p->item_y;
 if(!strcmp(p->mode,"about")){menu.x=90;popup.left=75;popup.right=161;popup.bottom=40;}
 if(!ClientToScreen(main_hwnd,&origin))return 84;action_main_origin=origin;
 menu.x+=origin.x;menu.y+=origin.y;item.x+=origin.x;item.y+=origin.y;
 if(!action_guard(p->mode)||!mouse_click(main_hwnd,menu,0)){event(p->mode,"blocked","Menu heading lost verified original target; no item click",85);return 85;}
 if(!wait_cancel(300))return 80;snapshot("menu-open");
 if(!action_guard(p->mode)||!observed_popup(origin,item,popup)){
  event(p->mode,"blocked","Expected CVI popup absent or capture stopped; no item click, no recovery key",86);return 86;
 }
 if(!mouse_click(main_hwnd,item,1)){event(p->mode,"blocked","Menu item target lost ownership",87);return 87;}
 event(p->mode,"opened","Selected fixed reviewed show-panel menu item",0);
 if(!wait_cancel(2000))return 80;
 if(!original_state("original-state-open.json",&current_optout,&current_access)||!find_panel(p)){
  event(p->mode,"unconfirmed","Expected auxiliary title/class/geometry not observed; no close attempted",88);return 88;
 }
 target=panel_hwnd;if(!activate_exact(target))return 84;snapshot("panel-open");
 if(!wait_cancel(2000))return 80;
 if(already_visible){event(p->mode,"preserved","Panel was initially visible and remains open",0);return 0;}
 /* Only these exact auxiliary panels have measured close_ctrl callbacks that
  * solely HidePanel. No generic close API, no main close and no warning retry. */
 if(!runtime_ok){event(p->mode,"skipped_close","Unreviewed loaded CVI runtime; leave panel open",0);return 0;}
 if(!action_guard(p->mode)||!runtime_ok||!find_panel(p)||panel_hwnd!=target||target==main_hwnd||cancelled()||!capture_proof())return 82;
 if(!PostMessageW(target,WM_SYSCOMMAND,SC_CLOSE,0)){event(p->mode,"skipped_close","Reviewed auxiliary close message failed; no retry",89);return 89;}
 event(p->mode,"auxiliary_close","Exact auxiliary close_ctrl dispatches its HidePanel-only callback",p->close_control);
 if(!wait_cancel(600))return 80;
 if(IsWindowVisible(target)){event(p->mode,"unconfirmed_close","Auxiliary remains visible; no retry",90);return 90;}
 return 0;
}
static int access_display(int wanted) {
 const char *word=wanted?"regensvc":"user";DWORD thread,mine;GUITHREADINFO gui;
 int attached=0,i,optout,level,ok=0;
 if(!action_guard(word))return 82;level=current_access;
 if(wanted==1&&initial_access==1&&level==1){event(word,"already_service","Initial service mode preserved; no keys",0);return 0;}
 if(wanted==0&&initial_access==0&&level==0){event(word,"already_user","Initial user mode already restored; no keys",0);return 0;}
 if(initial_access!=0||level!=(wanted?0:1)){event(word,"blocked","Only user-to-service display and return to original user level are permitted",91);return 91;}
 if(modifiers_down()||(GetKeyState(VK_CAPITAL)&1)){event(word,"blocked","Keyboard modifier or Caps Lock active; no keys",92);return 92;}
 thread=GetWindowThreadProcessId(main_hwnd,NULL);mine=GetCurrentThreadId();
 if(thread!=mine){attached=AttachThreadInput(mine,thread,TRUE);if(!attached)return 93;}
 SetForegroundWindow(main_hwnd);SetFocus(main_hwnd);ZeroMemory(&gui,sizeof(gui));gui.cbSize=sizeof(gui);
 if(!GetGUIThreadInfo(thread,&gui)||GetForegroundWindow()!=main_hwnd||gui.hwndFocus!=main_hwnd)goto done;
 /* Fixed lowercase sequences: original MainCallBack event7 -> SetAccessLevel,
  * GUI attributes/visibility only. No Enter, Escape, control edits or shell text. */
 for(i=0;word[i];i++){
  INPUT k[2];WORD vk=(WORD)(word[i]-'a'+'A');
  if(cancelled()||modifiers_down()||!capture_proof()||!GetGUIThreadInfo(thread,&gui)||gui.hwndFocus!=main_hwnd||GetForegroundWindow()!=main_hwnd)goto done;
  ZeroMemory(k,sizeof(k));k[0].type=INPUT_KEYBOARD;k[0].ki.wVk=vk;k[1]=k[0];k[1].ki.dwFlags=KEYEVENTF_KEYUP;
  if(SendInput(1,k,sizeof(INPUT))!=1)goto done;Sleep(40);
  if(SendInput(1,k+1,sizeof(INPUT))!=1&&SendInput(1,k+1,sizeof(INPUT))!=1)goto done;
  if(!wait_cancel(80))goto done;
 }
 ok=1;
 done:if(attached)AttachThreadInput(mine,thread,FALSE);
 if(!ok){event(word,"incomplete","Focus/capture/cancel guard stopped keys; no recovery keys",94);return 94;}
 if(!wait_cancel(1500))return 80;
 if(!original_state("original-state-access-after.json",&optout,&level)||optout!=1||level!=wanted){event(word,"unconfirmed","Expected access display state not observed; no retry",95);return 95;}
 event(word,"confirmed","Original access display changed; no device-setting callback in reviewed path",0);return 0;
}
static void skipped_items(void) {
 FILE *f=openout("skipped.jsonl","wb");if(!f)return;
 fputs("{\"item\":\"Original start, exit, restart, connection Warning OK\",\"reason\":\"Attach only; startup/reconnect can automatically send EMP:LBOBREAK 1\"}\n",f);
 fputs("{\"item\":\"RUN, STOP, Laser ON/OFF, HV, motor, parameter editors, temperature, sliders, mode selectors\",\"reason\":\"Device-changing controls excluded\"}\n",f);
 fputs("{\"item\":\"Empower/TCU Opt-out, fault reset, interlock/humidity/TDG overrides\",\"reason\":\"Changes device or safety state\"}\n",f);
 fputs("{\"item\":\"Escape, arbitrary shortcuts, factory/programmer modes, console, unknown buttons\",\"reason\":\"Not in reviewed display-only allowlist\"}\n",f);
 fclose(f);
}
static int driver_main(int argc,char **argv) {
 const char *mode;const Panel *panel=NULL;int preflight=0,rc=0,i,optout=-1,access=-1,ready=0;DWORD pid_before;FILE *f;char t[40];
 if(argc<3||argc>5)return 2;mode=argv[1];preflight=!strcmp(mode,"preflight");
 for(i=0;i<(int)(sizeof(panels)/sizeof(panels[0]));i++)if(!strcmp(mode,panels[i].mode))panel=&panels[i];
 if(!preflight&&!panel&&strcmp(mode,"regensvc")&&strcmp(mode,"user"))return 2;
 if(!preflight&&argc!=5)return 2;if(preflight&&argc!=3)return 2;
 if(strlen(argv[2])>MAX_PATH-64)return 2;strcpy(outdir,argv[2]);
 if(!CreateDirectoryA(outdir,NULL))return 3;timeline=openout("timeline.jsonl","wb");if(!timeline)return 3;
 if(!preflight){proof_path=argv[3];stop_path=argv[4];}
 event(mode,"begin","Attach-only original UI test; helper has no network interface",0);skipped_items();
 if(!processes()){rc=4;goto done;}pid_before=original_pid;
 if(!inventory_windows()||!screenshot()){event(mode,"blocked","Initial screenshot/inventory incomplete",4);rc=4;goto done;}
 snapshot("before");
 original_state("original-state-before.json",&optout,&access);
 ready=original_state_ok&&resource_ok&&runtime_ok&&optout==1&&(access==0||access==1)&&hold_thread==0&&find_main();
 if(!ready){event(mode,"capture_only","UI preflight failed; original untouched, passive capture may continue",20);rc=20;goto done;}
 if(!preflight){if(panel)rc=show_panel(panel);else rc=access_display(!strcmp(mode,"regensvc"));}
 if(!processes()||original_pid!=pid_before){event(mode,"blocked","Original process changed; stop subsequent actions",96);rc=96;}
 done:
 processes();snapshot("after");original_state("original-state.json",&optout,&access);utc(t,sizeof(t));
 f=openout("result.json","wb");if(f){
  fputs("{\"utc_guest_clock\":",f);js(f,t);fputs(",\"mode\":",f);js(f,mode);
  fprintf(f,",\"exit_code\":%d,\"original_pid\":%lu,\"original_exact_count\":%d,\"foreign_original_name\":%s,\"preflight_ready\":%s,\"emp_optout\":%d,\"gAccessLevel\":%d,\"main_hwnd\":%lu,\"blocking_warning_count\":%d,\"capture_proof_tick\":%lu,\"helper_udp_generated\":false,\"original_left_running\":%s}\n",rc,(unsigned long)original_pid,original_exact_count,original_foreign?"true":"false",ready?"true":"false",optout,access,(unsigned long)(uintptr_t)main_hwnd,warning_count,(unsigned long)proof_tick,original_exact_count==1?"true":"false");fclose(f);
 }
 event(mode,rc?"blocked_or_incomplete":"end","Before/after screenshots and inventories retained; original not closed",rc);
 fclose(timeline);return rc;
}
void WINAPI probe_entry(void) {
 int argc=0,i,rc=2;LPWSTR *wide=CommandLineToArgvW(GetCommandLineW(),&argc);char **args=NULL;
 if(wide&&argc>0&&argc<16){args=(char**)malloc((size_t)argc*sizeof(char*));if(args){
  for(i=0;i<argc;i++){int n=WideCharToMultiByte(CP_ACP,0,wide[i],-1,NULL,0,NULL,NULL);args[i]=(char*)malloc((size_t)n);if(!n||!args[i])ExitProcess(3);WideCharToMultiByte(CP_ACP,0,wide[i],-1,args[i],n,NULL,NULL);}rc=driver_main(argc,args);
 }}ExitProcess((UINT)rc);
}
unsigned long _tls_index=0;
