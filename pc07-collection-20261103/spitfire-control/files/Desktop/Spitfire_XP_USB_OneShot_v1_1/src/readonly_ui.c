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
static int initial_access=-1, current_access=-1, current_optout=-1, hold_thread=-1, action_start_access=-1;
static int action_skipped, context_serial;
static const char *skip_reason="",*context_reason="",*preflight_reason="";
static const char *failure_reason="";
static char failure_detail[1024];
static DWORD own_input_tick,context_input_tick;static int own_input_valid,context_input_valid;
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
static const char *native_failure_reason(int code) {
 if(code==20)return *preflight_reason?preflight_reason:"preflight_blocked";
 if(code==97)return *context_reason?context_reason:"input_context_unconfirmed";
 switch(code){
 case 4:return "evidence_write_failed";
 case 80:return "automation_cancelled";
 case 81:return "capture_proof_invalid";
 case 82:return "original_state_unconfirmed";
 case 84:return "foreground_unavailable";
 case 85:return "menu_heading_unconfirmed";
 case 86:return "menu_popup_unconfirmed";
 case 87:return "menu_item_unconfirmed";
 case 88:return "auxiliary_panel_unconfirmed";
 case 89:return "auxiliary_hide_failed";
 case 90:return "auxiliary_hide_unconfirmed";
 case 96:return "original_process_changed";
 default:return "native_action_blocked";
 }
}
static void event(const char *action,const char *phase,const char *detail,int code) {
 char t[40];utc(t,sizeof(t));
 if(code>0&&!*failure_reason&&strcmp(phase,"auxiliary_close")){
  failure_reason=native_failure_reason(code);
  _snprintf(failure_detail,sizeof(failure_detail),"%s",detail?detail:"");failure_detail[sizeof(failure_detail)-1]=0;
 }
 if(timeline) { fputs("{\"utc_guest_clock\":",timeline);js(timeline,t);fputs(",\"action\":",timeline);js(timeline,action);fputs(",\"phase\":",timeline);js(timeline,phase);fputs(",\"detail\":",timeline);js(timeline,detail);fprintf(timeline,",\"code\":%d}\n",code);fflush(timeline); }
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
static WCHAR loaded_cvi[MAX_PATH];static DWORD loaded_cvi_base;
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
 actual_exe[0]=actual_uir[0]=actual_cvi[0]=0;loaded_cvi[0]=0;loaded_cvi_base=0;
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
  if(!_wcsicmp(module.szModule,L"cvirte.dll")){cvi_count++;lstrcpynW(loaded_cvi,module.szExePath,MAX_PATH);loaded_cvi_base=(DWORD)(uintptr_t)module.modBaseAddr;}
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
/* Diagnostic-only first stage: observe CVI's virtual focus without activating a
 * window, calling the original runtime, or clearing any control's focus. The
 * offsets follow reviewed cvirte GetActiveCtrl/native WndProc disassembly.
 * These observations do not yet authorize additional UI input. */
static FILE *focus_file,*focus_map_file,*focus_raw_file;static HANDLE focus_process;
static int focus_read_word(DWORD address,DWORD *value,DWORD *error) {
 SIZE_T got=0;*value=0;
 if(address<0x10000u||address>0x7ffffffbu||(address&3u)){*error=ERROR_INVALID_ADDRESS;return 0;}
 if(!ReadProcessMemory(focus_process,(LPCVOID)(uintptr_t)address,value,4,&got)||got!=4){*error=GetLastError();return 0;}
 return 1;
}
static void focus_raw_dump(HWND h,const char *label,DWORD address) {
 BYTE data[1024];SIZE_T got=0;DWORD error=0;unsigned i;
 if(!focus_raw_file)return;
 if(address<0x10000u||address>0x7ffffbffu||(address&3u))error=ERROR_INVALID_ADDRESS;
 else if(!ReadProcessMemory(focus_process,(LPCVOID)(uintptr_t)address,data,sizeof(data),&got)){error=GetLastError();got=0;}
 fprintf(focus_raw_file,"{\"read_only\":true,\"diagnostic_only\":true,\"hwnd\":%lu,\"label\":",(unsigned long)(uintptr_t)h);js(focus_raw_file,label);
 fprintf(focus_raw_file,",\"address\":%lu,\"bytes\":%lu,\"win32_error\":%lu,\"hex\":\"",(unsigned long)address,(unsigned long)got,(unsigned long)error);
 for(i=0;i<got;i++)fprintf(focus_raw_file,"%02x",(unsigned)data[i]);fputs("\"}\n",focus_raw_file);
}
static void focus_control_map(HWND h,DWORD wrapper_base) {
 DWORD list_handle=0,list_base=0,magic=0,item_size=0,count=0,error=0,i;
 int valid=0;if(!focus_map_file)return;
 if(!focus_read_word(wrapper_base+0xd4,&list_handle,&error)||!focus_read_word(list_handle,&list_base,&error))goto header;
 if(list_base<0x10000u||list_base>0x7ffffb00u||(list_base&3u)){error=ERROR_INVALID_ADDRESS;goto header;}
 if(!focus_read_word(list_base+4,&magic,&error)||!focus_read_word(list_base+0x10,&item_size,&error)||!focus_read_word(list_base+0x14,&count,&error))goto header;
 valid=magic==0xb00bdeedu&&item_size==4&&count<=256;
 header:
 fprintf(focus_map_file,"{\"kind\":\"control_list\",\"read_only\":true,\"diagnostic_only\":true,\"hwnd\":%lu,\"wrapper_base\":%lu,\"list_handle\":%lu,\"list_base\":%lu,\"magic\":%lu,\"item_size\":%lu,\"count\":%lu,\"valid\":%s,\"win32_error\":%lu}\n",(unsigned long)(uintptr_t)h,(unsigned long)wrapper_base,(unsigned long)list_handle,(unsigned long)list_base,(unsigned long)magic,(unsigned long)item_size,(unsigned long)count,valid?"true":"false",(unsigned long)error);
 if(!valid)return;
 for(i=0;i<count;i++){
  DWORD control_handle=0,control_base=0,control_type=0,public_id=0,native_id=0;int good=0;error=0;
  if(!focus_read_word(list_base+0x18+i*4,&control_handle,&error)||!focus_read_word(control_handle,&control_base,&error))goto control;
  if(control_base<0x10000u||control_base>0x7fffff00u||(control_base&3u)){error=ERROR_INVALID_ADDRESS;goto control;}
  if(!focus_read_word(control_base,&control_type,&error)||!focus_read_word(control_base+0x28,&public_id,&error)||!focus_read_word(control_base+0xac,&native_id,&error))goto control;
  good=control_type==0xeb19u&&public_id>0&&public_id<=256;
  control:
  fprintf(focus_map_file,"{\"kind\":\"control\",\"read_only\":true,\"diagnostic_only\":true,\"hwnd\":%lu,\"index\":%lu,\"control_handle\":%lu,\"control_base\":%lu,\"control_type\":%lu,\"public_id\":%lu,\"native_id\":%lu,\"valid\":%s,\"win32_error\":%lu}\n",(unsigned long)(uintptr_t)h,(unsigned long)i,(unsigned long)control_handle,(unsigned long)control_base,(unsigned long)control_type,(unsigned long)public_id,(unsigned long)native_id,good?"true":"false",(unsigned long)error);
 }
}
static BOOL CALLBACK focus_probe_cb(HWND h,LPARAM param) {
 DWORD pid=0,window_handle=0,window_base=0,window_callback=0,back_reference=0,wrapper_handle=0,wrapper_base=0,wrapper_type=0,wrapper_id=0,handle=0,base=0,native_hwnd=0,field44=0,field78=0,holder=0,node=0,kind=0,selector=0,error=0;
 WCHAR title[512],cls[256];int valid=0,stage=0;LONG extra;char t[40];(void)param;
 GetWindowThreadProcessId(h,&pid);if(pid!=original_pid)return TRUE;
 GetClassNameW(h,cls,256);if(_wcsicmp(cls,L"CVIRTLVDChild4194304"))return TRUE;
 window_text(h,title,512);extra=GetClassLongA(h,GCL_CBWNDEXTRA);utc(t,sizeof(t));
 if(extra<4){error=ERROR_INVALID_DATA;goto done;}
 stage=1;SetLastError(0);window_handle=(DWORD)GetWindowLongA(h,0);
 if(!window_handle){error=GetLastError();goto done;}
 focus_raw_dump(h,"window_extra_0",window_handle);
 stage=2;if(!focus_read_word(window_handle,&window_base,&error))goto done;
 focus_raw_dump(h,"window_base",window_base);
 if(window_base<0x10000u||window_base>0x7fffff00u||(window_base&3u)){error=ERROR_INVALID_ADDRESS;goto done;}
 if(!focus_read_word(window_base+0x58,&native_hwnd,&error)||native_hwnd!=(DWORD)(uintptr_t)h){if(!error)error=ERROR_INVALID_DATA;goto done;}
 /* 0x684799c5 dispatches the platform WINDOW callback at+0x2c, passing
  * its userdata at+0x50. Reviewed callback0x685cebb1 receives the generic
  * PANEL handle there; the public CVI wrapper is a third, separate object. */
 stage=3;if(!focus_read_word(window_base+0x2c,&window_callback,&error)||window_callback!=loaded_cvi_base+0x1aebb1u){if(!error)error=ERROR_INVALID_DATA;goto done;}
 if(!focus_read_word(window_base+0x50,&handle,&error))goto done;
 stage=4;if(!focus_read_word(handle,&base,&error))goto done;
 focus_raw_dump(h,"generic_panel_base",base);
 if(base<0x10000u||base>0x7fffff00u||(base&3u)){error=ERROR_INVALID_ADDRESS;goto done;}
 stage=5;if(!focus_read_word(base+0x5c,&back_reference,&error)||back_reference!=window_handle){if(!error)error=ERROR_INVALID_DATA;goto done;}
 if(!focus_read_word(base+0x74,&wrapper_handle,&error)||!focus_read_word(wrapper_handle,&wrapper_base,&error))goto done;
 if(wrapper_base<0x10000u||wrapper_base>0x7fffff00u||(wrapper_base&3u)){error=ERROR_INVALID_ADDRESS;goto done;}
 if(!focus_read_word(wrapper_base,&wrapper_type,&error)||!focus_read_word(wrapper_base+0x28,&wrapper_id,&error))goto done;
 stage=6;if(!focus_read_word(base+0x44,&field44,&error)||!focus_read_word(base+0x78,&field78,&error))goto done;
 stage=7;if(!focus_read_word(base+0x54,&holder,&error))goto done;
 /* Inspect remembered selection even when native query would short-circuit
  * on field44==0. Inactive panels may retain a target for later activation. */
 if(!holder&&!field44){valid=1;goto done;}
 stage=8;if(!focus_read_word(holder,&node,&error))goto done;
 if(!node&&!field44){valid=1;goto done;}
 if(node<0x10000u||node>0x7fffffe0u||(node&3u)){error=ERROR_INVALID_ADDRESS;goto done;}
 stage=9;if(!focus_read_word(node+8,&kind,&error)||!focus_read_word(node+12,&selector,&error))goto done;
 valid=1;
 done:
 if(wrapper_type==0xeb13u&&native_hwnd==(DWORD)(uintptr_t)h)focus_control_map(h,wrapper_base);
 fputs("{\"utc_guest_clock\":",focus_file);js(focus_file,t);
 fprintf(focus_file,",\"read_only\":true,\"diagnostic_only\":true,\"pid\":%lu,\"hwnd\":%lu,\"visible\":%s,\"enabled\":%s,\"title\":",(unsigned long)pid,(unsigned long)(uintptr_t)h,IsWindowVisible(h)?"true":"false",IsWindowEnabled(h)?"true":"false");jw(focus_file,title);
 fputs(",\"class\":",focus_file);jw(focus_file,cls);
 fprintf(focus_file,",\"class_extra_bytes\":%ld,\"window_handle\":%lu,\"window_base\":%lu,\"window_callback\":%lu,\"back_reference\":%lu,\"wrapper_handle\":%lu,\"wrapper_base\":%lu,\"wrapper_type\":%lu,\"wrapper_id\":%lu,\"native_handle\":%lu,\"native_base\":%lu,\"native_hwnd\":%lu,\"field_44\":%lu,\"field_78\":%lu,\"selection_holder\":%lu,\"selection_node\":%lu,\"selection_kind\":%lu,\"selection_value\":%lu,\"chain_valid\":%s,\"stage\":%d,\"win32_error\":%lu}\n",extra,(unsigned long)window_handle,(unsigned long)window_base,(unsigned long)window_callback,(unsigned long)back_reference,(unsigned long)wrapper_handle,(unsigned long)wrapper_base,(unsigned long)wrapper_type,(unsigned long)wrapper_id,(unsigned long)handle,(unsigned long)base,(unsigned long)native_hwnd,(unsigned long)field44,(unsigned long)field78,(unsigned long)holder,(unsigned long)node,(unsigned long)kind,(unsigned long)selector,valid?"true":"false",stage,(unsigned long)error);
 return TRUE;
}
static void focus_probe(void) {
 focus_file=openout("cvi-focus.jsonl","wb");if(!focus_file)return;
 if(!original_state_ok||!runtime_ok){fputs("{\"read_only\":true,\"diagnostic_only\":true,\"blocked\":\"Exact original state/runtime identity required\"}\n",focus_file);fclose(focus_file);focus_file=NULL;return;}
 focus_map_file=openout("cvi-focus-map.jsonl","wb");
 focus_raw_file=openout("cvi-focus-raw.jsonl","wb");
 focus_process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);
 if(focus_process){EnumWindows(focus_probe_cb,0);CloseHandle(focus_process);}
 else fprintf(focus_file,"{\"read_only\":true,\"diagnostic_only\":true,\"open_process_error\":%lu}\n",(unsigned long)GetLastError());
 if(focus_map_file)fclose(focus_map_file);focus_map_file=NULL;
 if(focus_raw_file)fclose(focus_raw_file);focus_raw_file=NULL;
 fclose(focus_file);focus_file=NULL;focus_process=NULL;
}
static int cancelled(void) {
 return (stop_path&&GetFileAttributesA(stop_path)!=INVALID_FILE_ATTRIBUTES)||(GetAsyncKeyState(VK_F12)&0x8000);
}
static int wait_cancel(DWORD ms) {
 DWORD start=GetTickCount();do{if(cancelled())return 0;Sleep(50);}while((DWORD)(GetTickCount()-start)<ms);return 1;
}
static int any_held_input(void);
static int input_tick_matches(DWORD tick) {
 LASTINPUTINFO last;ZeroMemory(&last,sizeof(last));last.cbSize=sizeof(last);
 return !cancelled()&&!any_held_input()&&GetLastInputInfo(&last)&&last.dwTime==tick;
}
static int decimal(const char *s,DWORD *out) {
 DWORD v=0;if(!*s)return 0;
 for(;*s;s++){DWORD d=(DWORD)(*s-'0');if(d>9||v>429496729u||(v==429496729u&&d>5))return 0;v=v*10+d;}*out=v;return 1;
}
/* Root orchestrator writes this proof only after reading live passive capture status.
 * This is a freshness/coordination guard, not a cryptographic authorization token. */
static int capture_proof_once(void) {
 static const char *keys[]={"schema=","ui_ready=","write_commands=","observed_pairs=","updated_tick=","original_pid=","initial_access="};
 char data[4096],line[512],extra;DWORD values[7]={0},used=0,got=0;unsigned seen=0;int i,ok=1;FILE *copy;HANDLE file;size_t at=0,start,n;
 if(!proof_path)return -1;
 /* XP's CRT fopen can deny delete sharing. Permit the publisher's atomic
  * replacement and release the snapshot handle BEFORE parsing/evidence I/O. */
 file=CreateFileA(proof_path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
 if(file==INVALID_HANDLE_VALUE)return -1;
 for(;;){
  if(used==sizeof(data)){
   if(!ReadFile(file,&extra,1,&got,NULL)){CloseHandle(file);return -1;}
   CloseHandle(file);if(got)return 0;break;
  }
  if(!ReadFile(file,data+used,(DWORD)sizeof(data)-used,&got,NULL)){CloseHandle(file);return -1;}
  if(!got){CloseHandle(file);break;}used+=got;
 }
 copy=openout("capture-proof.txt","wb");if(copy){fwrite(data,1,used,copy);fclose(copy);}
 while(at<used){
  start=at;while(at<used&&data[at]!='\n')at++;n=at-start;if(at<used)at++;
  if(n&&data[start+n-1]=='\r')n--;
  if(n>=sizeof(line)){ok=0;break;}
  for(i=0;i<(int)n;i++)if(!data[start+i]||data[start+i]=='\r'){ok=0;break;}
  if(!ok)break;
  memcpy(line,data+start,n);line[n]=0;if(!line[0])continue;
  for(i=0;i<7;i++)if(!strncmp(line,keys[i],strlen(keys[i])))break;
  if(i==7||(seen&(1u<<i))){ok=0;break;}seen|=1u<<i;
  if(i==0){if(strcmp(line+strlen(keys[i]),"spitfire-passive-v1"))ok=0;}
  else if(!decimal(line+strlen(keys[i]),&values[i]))ok=0;
 }
 if(!ok)return 0;if(seen!=127)return -1;
 if(values[1]!=1||values[2]!=0||values[3]!=1||values[5]!=original_pid||values[6]>1||(DWORD)(GetTickCount()-values[4])>5000)return 0;
 proof_tick=values[4];initial_access=(int)values[6];return 1;
}
static int capture_proof(void) {
 int i,rc;
 /* Startup or an interrupted publication can leave a missing/incomplete file.
  * Retry missing/incomplete snapshots
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
 DWORD target=GetWindowThreadProcessId(h,NULL),mine=GetCurrentThreadId(),foreground_error,raise_error;
 int attached=0,foreground_result,raise_result;char detail[256];
 if(!context_input_valid||!input_tick_matches(context_input_tick)){context_reason="external_input_detected";event("focus","context_blocked",context_reason,97);return 0;}
 if(target!=mine){attached=AttachThreadInput(mine,target,TRUE);if(!attached){event("focus","attach_failed","AttachThreadInput rejected; no input sent",(int)GetLastError());return 0;}}
 SetLastError(0);foreground_result=SetForegroundWindow(h);foreground_error=GetLastError();
 SetLastError(0);raise_result=BringWindowToTop(h);raise_error=GetLastError();
 if(attached)AttachThreadInput(mine,target,FALSE);
 if(!wait_cancel(180)){event("focus","cancelled","STOP file/F12 interrupted foreground wait; no input sent",80);return 0;}
 if(GetForegroundWindow()!=h){
  _snprintf(detail,sizeof(detail),"Target HWND=%lu actual=%lu SetForegroundWindow=%d last_error=%lu BringWindowToTop=%d last_error=%lu attached=%d",(unsigned long)(uintptr_t)h,(unsigned long)(uintptr_t)GetForegroundWindow(),foreground_result,(unsigned long)foreground_error,raise_result,(unsigned long)raise_error,attached);
  detail[sizeof(detail)-1]=0;event("focus","foreground_mismatch",detail,84);return 0;
 }
 return 1;
}
static int modifiers_down(void) {
 return (GetAsyncKeyState(VK_SHIFT)&0x8000)||(GetAsyncKeyState(VK_CONTROL)&0x8000)||
        (GetAsyncKeyState(VK_MENU)&0x8000)||(GetAsyncKeyState(VK_LWIN)&0x8000)||
        (GetAsyncKeyState(VK_RWIN)&0x8000)||(GetAsyncKeyState(VK_LBUTTON)&0x8000)||
        (GetAsyncKeyState(VK_RBUTTON)&0x8000);
}
static POINT action_main_origin;
static int menu_target_unchanged(HWND expected,POINT point,int allow_menu);
static int context_guard(const char *label,int phase,HWND owned);
static int recheck_hidden_target(void);
static int mouse_click(HWND expected,POINT point,int allow_menu) {
 INPUT input[2];HWND under;DWORD owner=0;POINT current;UINT down,up;
 if(cancelled()||modifiers_down()||GetForegroundWindow()!=main_hwnd)return 0;
 if(!SetCursorPos(point.x,point.y)||!wait_cancel(80))return 0;GetCursorPos(&current);
 if(current.x!=point.x||current.y!=point.y)return 0;
 under=WindowFromPoint(point);GetWindowThreadProcessId(under,&owner);
 if(owner!=original_pid||(!allow_menu&&under!=expected&&!IsChild(expected,under))||cancelled()||!capture_proof())return 0;
 if(!context_guard(allow_menu?"before_menu_item":"before_menu_heading",allow_menu?1:0,NULL))return 0;
 if(allow_menu&&!recheck_hidden_target())return 0;
 /* No delay or file hashing between this final geometry/popup check and input. */
 if(!menu_target_unchanged(expected,point,allow_menu))return 0;
 if(!context_input_valid||!input_tick_matches(context_input_tick)){context_reason="external_input_detected";event("mouse","context_blocked",context_reason,97);return 0;}
 ZeroMemory(input,sizeof(input));input[0].type=INPUT_MOUSE;input[0].mi.dwFlags=MOUSEEVENTF_LEFTDOWN;
 input[1].type=INPUT_MOUSE;input[1].mi.dwFlags=MOUSEEVENTF_LEFTUP;
 down=SendInput(1,input,sizeof(INPUT));Sleep(120);
 /* Always release only our own held button, even when cancellation arrives. */
 up=SendInput(1,input+1,sizeof(INPUT));if(up!=1)up=SendInput(1,input+1,sizeof(INPUT));
 if(down==1&&up==1){LASTINPUTINFO last;ZeroMemory(&last,sizeof(last));last.cbSize=sizeof(last);own_input_valid=GetLastInputInfo(&last);if(own_input_valid)own_input_tick=last.dwTime;}
 return down==1&&up==1&&own_input_valid;
}
typedef struct {const char *mode;const WCHAR *menu,*title;int width0,height0,width1,height1,item_y,close_control;DWORD panel_global,menu_id,item_id,callback;} Panel;
static const Panel panels[]={
 {"temperature",L"Temperature Control",L"Temperature Control",480,250,480,480,76,6,0x414188u,4,8,0x40734du},
 {"timing",L"Timing and High Voltage",L"Timing and High Voltage",390,446,750,446,60,21,0x414180u,4,7,0x40730bu},
 {"faults",L"Active Faults",L"Active Faults",720,580,720,580,44,33,0x414190u,4,6,0x4072eau},
 {"setup",L"Empower Setup",L"Empower Setup",544,250,544,480,28,12,0x41418cu,4,5,0x4072c9u},
 {"about",L"About",L"Help",500,277,500,277,28,9,0x414194u,9,10,0x40732cu}
};
static const Panel *find_panel_spec,*action_panel_spec;static HWND panel_hwnd,action_hidden_hwnd;static int panel_count,panel_wanted_visible;
static BOOL CALLBACK panel_cb(HWND h,LPARAM x) {
 DWORD pid=0;WCHAR title[512],cls[256];RECT r,c;int level=current_access;(void)x;
 GetWindowThreadProcessId(h,&pid);if(pid!=original_pid||(IsWindowVisible(h)?1:0)!=panel_wanted_visible||!IsWindowEnabled(h))return TRUE;
 window_text(h,title,512);GetClassNameW(h,cls,256);GetWindowRect(h,&r);GetClientRect(h,&c);
 if(!_wcsicmp(title,find_panel_spec->title)&&!_wcsicmp(cls,L"CVIRTLVDChild4194304")&&
    c.left==0&&c.top==0&&c.right==(level?find_panel_spec->width1:find_panel_spec->width0)&&
    c.bottom==(level?find_panel_spec->height1:find_panel_spec->height0)&&(!panel_wanted_visible||(r.left>=0&&r.top>=0&&
    r.right<=GetSystemMetrics(SM_CXSCREEN)&&r.bottom<=GetSystemMetrics(SM_CYSCREEN)))){panel_hwnd=h;panel_count++;}
 return TRUE;
}
static int find_panel(const Panel *p) {find_panel_spec=p;panel_wanted_visible=1;panel_hwnd=NULL;panel_count=0;EnumWindows(panel_cb,0);return panel_count==1;}
static int find_hidden_panel(const Panel *p) {find_panel_spec=p;panel_wanted_visible=0;panel_hwnd=NULL;panel_count=0;EnumWindows(panel_cb,0);return panel_count==1;}
typedef struct {
 HWND hwnd;DWORD window_handle,window_base,menu_handle,menu_base;unsigned stage;DWORD read_error;
 DWORD public_bar_handle,public_menu_handle,public_menu_id,public_item_handles[4],public_item_ids[4],callbacks[4];
 DWORD native_item_addresses[4],native_submenus[4],native_separator[4];
 DWORD row_height,first_visible,last_visible;unsigned item_count,selected_index,enabled[4],checked[4];
 RECT window_rect,client_rect,native_rect,item_rect;POINT client_origin,hit;
 char labels[4][64];
} MenuSnapshot;
typedef struct {
 HWND hwnd;unsigned stage;DWORD read_error,public_bar_handle,native_bar_handle,native_bar_base;
 DWORD public_menu_handles[3],public_menu_ids[3],native_menu_handles[3],native_item_addresses[3];
 DWORD font_index,font_base,widths_pointer,bearing_pointer;DWORD font_measure_kind,runtime_modes[3],runtime_platform;BYTE font_logfont[60];LONG gdi_widths[3],font_metrics[4];BYTE font_data[64];short widths[256],bearings[256],padding;
 unsigned selected_index;RECT client_rect,bar_rect,heading_rects[3];POINT client_origin,hit;char labels[3][64];
} HeaderSnapshot;
static HeaderSnapshot heading_snapshot;static int heading_frozen;

static MenuSnapshot menu_snapshot,menu_candidate;
static int popup_matches,popup_seen_count,menu_frozen,menu_serial;static HWND popup_hwnd;
static const char *menu_reason="",*menu_detail="";
static int inspect_popup(HWND h,const Panel *p,MenuSnapshot *m);
static int menu_observation(const MenuSnapshot *m,int ok,const char *phase);
static BOOL CALLBACK popup_cb(HWND h,LPARAM x) {
 DWORD pid=0;WCHAR cls[128];MenuSnapshot m;(void)x;GetWindowThreadProcessId(h,&pid);
 if(pid!=original_pid||!IsWindowVisible(h))return TRUE;
 GetClassNameW(h,cls,128);if(_wcsicmp(cls,L"CVIRTLVMenuWnd4194304"))return TRUE;
 popup_seen_count++;
 if(inspect_popup(h,action_panel_spec,&m)){popup_matches++;menu_candidate=m;}
 else menu_observation(&m,0,"rejected");
 return TRUE;
}
static int observed_popup(int freeze) {
 popup_matches=popup_seen_count=0;ZeroMemory(&menu_candidate,sizeof(menu_candidate));
 menu_reason="";menu_detail="";EnumWindows(popup_cb,0);
 if(popup_seen_count!=1||popup_matches!=1){
  if(!*menu_reason){menu_reason="menu_popup_unconfirmed";menu_detail="Exactly one identified original menu popup is required.";}
  return 0;
 }
 if(!freeze&&(!menu_frozen||memcmp(&menu_candidate,&menu_snapshot,sizeof(menu_snapshot)))){
  menu_reason="menu_popup_unconfirmed";menu_detail="Menu identity, geometry, item states or HWND changed before input.";
  menu_observation(&menu_candidate,0,"changed");return 0;
 }
 if(freeze){menu_snapshot=menu_candidate;menu_frozen=1;popup_hwnd=menu_snapshot.hwnd;if(!menu_observation(&menu_snapshot,1,"selected")){menu_reason="evidence_write_failed";menu_detail="Could not save verified menu layout evidence.";return 0;}}
 return 1;
}
typedef struct {
 DWORD window_handle,window_base,panel_handle,panel_base,wrapper_handle,wrapper_base;
 DWORD wrapper_id,active,holder,node,kind,selector,native_id,public_id,error;
 int valid,matches;
} FocusRecord;
/* Classification is intentionally independent of HWND activation and input.
 * A remembered numeric control remains disallowed even when active==0. */
static int focus_policy(int valid,DWORD active,DWORD node,DWORD kind,DWORD public_id,int matches) {
 if(!valid)return 0;
 if(!node)return active==0;
 if(kind==2)return 1;
 return kind==3&&public_id==3&&matches==1;
}
static int readable_base(DWORD p) {return p>=0x10000u&&p<=0x7ffffb00u&&!(p&3u);}
static int observe_main_focus(FocusRecord *f) {
 DWORD v=0,type=0,main_id=0,back=0,callback=0,list_handle=0,list_base=0,magic=0,size=0,count=0,i;
 ZeroMemory(f,sizeof(*f));
 f->window_handle=(DWORD)GetWindowLongA(main_hwnd,0);
 if(!focus_read_word(f->window_handle,&f->window_base,&f->error)||!readable_base(f->window_base))return 0;
 if(!focus_read_word(f->window_base+0x58,&v,&f->error)||v!=(DWORD)(uintptr_t)main_hwnd)return 0;
 if(!focus_read_word(f->window_base+0x2c,&callback,&f->error)||callback!=loaded_cvi_base+0x1aebb1u)return 0;
 if(!focus_read_word(f->window_base+0x50,&f->panel_handle,&f->error)||!focus_read_word(f->panel_handle,&f->panel_base,&f->error)||!readable_base(f->panel_base))return 0;
 if(!focus_read_word(f->panel_base+0x5c,&back,&f->error)||back!=f->window_handle)return 0;
 if(!focus_read_word(f->panel_base+0x78,&callback,&f->error)||callback!=loaded_cvi_base+0x16aaaeu)return 0;
 if(!focus_read_word(f->panel_base+0x74,&f->wrapper_handle,&f->error)||!focus_read_word(f->wrapper_handle,&f->wrapper_base,&f->error)||!readable_base(f->wrapper_base))return 0;
 if(!focus_read_word(f->wrapper_base,&type,&f->error)||type!=0xeb13u||!focus_read_word(f->wrapper_base+0xa0,&v,&f->error)||v!=f->panel_handle)return 0;
 if(!focus_read_word(f->wrapper_base+0x28,&f->wrapper_id,&f->error)||!focus_read_word(0x41417cu,&main_id,&f->error)||f->wrapper_id!=main_id)return 0;
 if(!focus_read_word(f->panel_base+0x44,&f->active,&f->error)||!focus_read_word(f->panel_base+0x54,&f->holder,&f->error))return 0;
 if(f->holder&&!focus_read_word(f->holder,&f->node,&f->error))return 0;
 if(!f->node){f->valid=1;return 1;}
 if(!readable_base(f->node)||!focus_read_word(f->node+8,&f->kind,&f->error)||!focus_read_word(f->node+12,&f->selector,&f->error))return 0;
 if(f->kind!=3){f->valid=1;return 1;}
 if(f->selector>=256)return 0;f->native_id=f->selector+1;
 if(!focus_read_word(f->wrapper_base+0xd4,&list_handle,&f->error)||!focus_read_word(list_handle,&list_base,&f->error)||!readable_base(list_base))return 0;
 if(!focus_read_word(list_base+4,&magic,&f->error)||magic!=0xb00bdeedu||!focus_read_word(list_base+0x10,&size,&f->error)||size!=4||!focus_read_word(list_base+0x14,&count,&f->error)||!count||count>256)return 0;
 for(i=0;i<count;i++){
  DWORD ch=0,cb=0,id=0,native_id=0;
  if(!focus_read_word(list_base+0x18+i*4,&ch,&f->error)||!focus_read_word(ch,&cb,&f->error)||!readable_base(cb))return 0;
  if(!focus_read_word(cb,&type,&f->error)||type!=0xeb19u||!focus_read_word(cb+0x28,&id,&f->error)||!id||id>256||!focus_read_word(cb+0xac,&native_id,&f->error))return 0;
  if(native_id==f->native_id){f->matches++;f->public_id=id;}
 }
 f->valid=f->matches==1;return f->valid;
}
/* Read-only translation of the reviewed CVI7.1 custom-menu hit-test.
 * Addresses below are relative to the hash-locked runtime, never invoked. */
static int menu_read_bytes(DWORD address,void *data,DWORD size,DWORD *error) {
 SIZE_T got=0;
 if(!size||size>512||address<0x10000u||address>0x7fffffffu-size){*error=ERROR_INVALID_ADDRESS;return 0;}
 if(!ReadProcessMemory(focus_process,(LPCVOID)(uintptr_t)address,data,size,&got)||got!=size){*error=GetLastError();return 0;}
 return 1;
}
static int menu_list_entries(DWORD handle,DWORD *entries,unsigned expected,DWORD *error) {
 DWORD b=0,v=0;unsigned i;
 if(!focus_read_word(handle,&b,error)||!readable_base(b))return 0;
 if(!focus_read_word(b+4,&v,error)||v!=0xb00bdeedu||!focus_read_word(b+0x10,&v,error)||v!=4||!focus_read_word(b+0x14,&v,error)||v!=expected)return 0;
 for(i=0;i<expected;i++)if(!focus_read_word(b+0x18+4*i,&entries[i],error)||!readable_base(entries[i]))return 0;
 return 1;
}
static int menu_expected_items(const Panel *p,unsigned *count,unsigned *selected,DWORD *ids,DWORD *callbacks,const char **labels) {
 static const DWORD view_ids[]={5,6,7,8},view_callbacks[]={0x4072c9u,0x4072eau,0x40730bu,0x40734du};
 static const char *view_labels[]={"Empower Setup","Active Faults","Timing and High Voltage","Temperature Control"};
 unsigned i,found=0;
 if(!p)return 0;
 if(p->menu_id==4){*count=4;for(i=0;i<4;i++){ids[i]=view_ids[i];callbacks[i]=view_callbacks[i];labels[i]=view_labels[i];if(p->item_id==ids[i]&&p->callback==callbacks[i]){*selected=i;found++;}}}
 else if(p->menu_id==9&&p->item_id==10&&p->callback==0x40732cu){*count=1;*selected=0;ids[0]=10;callbacks[0]=0x40732cu;labels[0]="About";found=1;}
 return found==1;
}
/* The original CVI menu bar uses its cached font metrics, not fixed Windows
 * coordinates. These readers reproduce only the reviewed ASCII, initialized
 * metric paths. Unknown font paths stop before opening any menu. */
/* A hosted IDE may supply a nonstandard DC. The reviewed ordinary runtime path
 * uses a common display DC (class style 0); require the standalone DLL binding. */
static int standalone_cvi_runtime(void) {
 HANDLE snapshot;MODULEENTRY32W module;int ok=0,count=0;DWORD error;
 snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,original_pid);if(snapshot==INVALID_HANDLE_VALUE)return 0;
 ZeroMemory(&module,sizeof(module));module.dwSize=sizeof(module);
 if(!Module32FirstW(snapshot,&module))goto done;
 do{
  if(!_wcsicmp(module.szModule,L"cvi.dll"))goto done;
  if(!_wcsicmp(module.szModule,L"cvirte.dll")){
   if((DWORD)(uintptr_t)module.modBaseAddr!=loaded_cvi_base||_wcsicmp(module.szExePath,loaded_cvi))goto done;
   count++;
  }
 }while(Module32NextW(snapshot,&module));
 error=GetLastError();ok=error==ERROR_NO_MORE_FILES&&count==1;
 done:CloseHandle(snapshot);return ok;
}
/* The original uses GDI directly for non-ANSI or corrected font metrics. Query
 * its HFONT without selecting it, then measure a private clone in our own DC.
 * No original window/DC/font/runtime object is changed or invoked. */
static int heading_gdi_widths(HeaderSnapshot *h) {
 DWORD error=0,native_font=0,modes_after[3]={0},platform_after=0;BYTE font_after[64];
 LOGFONTA logical,copy,after;TEXTMETRICA metrics;HDC screen=NULL,dc=NULL;HFONT font=NULL;HGDIOBJ old=NULL;SIZE extent;
 unsigned short flags=0;short style=0,mono=0,ascent=0,descent=0,leading=0;unsigned i;int ok=0;
 static const char *labels[]={"File","View","Help"};
 memcpy(&flags,h->font_data+0x20,2);memcpy(&style,h->font_data+0x12,2);memcpy(&mono,h->font_data+0x1c,2);
 if(!(flags&4)||(style&2)||!((flags&0x10)||((flags&8)&&mono<=0&&(flags&2)&&(flags&1))))return 0;
 if(sizeof(logical)!=sizeof(h->font_logfont)||!standalone_cvi_runtime())return 0;
 if(!menu_read_bytes(loaded_cvi_base+0x24197cu,h->runtime_modes,sizeof(h->runtime_modes),&error)||!focus_read_word(loaded_cvi_base+0x268bfcu,&h->runtime_platform,&error))return 0;
 if(h->runtime_modes[0]&&!h->runtime_modes[1]&&!h->runtime_modes[2])return 0;
 memcpy(&native_font,h->font_data+8,4);if(!native_font)return 0;
 ZeroMemory(&logical,sizeof(logical));ZeroMemory(&copy,sizeof(copy));ZeroMemory(&after,sizeof(after));ZeroMemory(&metrics,sizeof(metrics));
 if(GetObjectA((HGDIOBJ)(uintptr_t)native_font,sizeof(logical),&logical)!=sizeof(logical)||logical.lfEscapement||logical.lfOrientation)return 0;
 memcpy(h->font_logfont,&logical,sizeof(logical));
 font=CreateFontIndirectA(&logical);if(!font)goto done;
 if(GetObjectA(font,sizeof(copy),&copy)!=sizeof(copy)||memcmp(&logical,&copy,sizeof(logical)))goto done;
 screen=GetDC(NULL);if(!screen)goto done;dc=CreateCompatibleDC(screen);if(!dc||GetMapMode(dc)!=MM_TEXT)goto done;
 old=SelectObject(dc,font);if(!old||old==HGDI_ERROR)goto done;
 if(!GetTextMetricsA(dc,&metrics))goto done;
 memcpy(&ascent,h->font_data+0x16,2);memcpy(&descent,h->font_data+0x18,2);memcpy(&leading,h->font_data+0x1a,2);
 if(metrics.tmAscent!=ascent||metrics.tmDescent!=descent||metrics.tmExternalLeading!=leading||metrics.tmHeight!=metrics.tmAscent+metrics.tmDescent)goto done;
 if((flags&2)&&((metrics.tmCharSet!=ANSI_CHARSET)?1:0)!=((flags&1)?1:0))goto done;
 h->font_metrics[0]=metrics.tmAscent;h->font_metrics[1]=metrics.tmDescent;h->font_metrics[2]=metrics.tmExternalLeading;h->font_metrics[3]=metrics.tmCharSet;
 for(i=0;i<3;i++){
  int len=(int)strlen(labels[i]);ZeroMemory(&extent,sizeof(extent));
  /* Native code narrows cx to signed16, then rejects values below byte length.
   * Only positive unsaturated, bounded widths can define our safe hitbox. */
  if(!(h->runtime_platform==3?GetTextExtentPointA(dc,labels[i],len,&extent):GetTextExtentPoint32A(dc,labels[i],len,&extent))||extent.cx<len||extent.cx>160||extent.cy!=metrics.tmHeight)goto done;
  h->gdi_widths[i]=extent.cx;
 }
 if(GetObjectA((HGDIOBJ)(uintptr_t)native_font,sizeof(after),&after)!=sizeof(after)||memcmp(&logical,&after,sizeof(logical)))goto done;
 if(!menu_read_bytes(h->font_base,font_after,sizeof(font_after),&error)||memcmp(h->font_data,font_after,sizeof(font_after))||!menu_read_bytes(loaded_cvi_base+0x24197cu,modes_after,sizeof(modes_after),&error)||memcmp(h->runtime_modes,modes_after,sizeof(modes_after))||!focus_read_word(loaded_cvi_base+0x268bfcu,&platform_after,&error)||platform_after!=h->runtime_platform||!standalone_cvi_runtime())goto done;
 h->font_measure_kind=2;ok=1;
 done:
 if(old&&old!=HGDI_ERROR)SelectObject(dc,old);if(dc)DeleteDC(dc);if(screen)ReleaseDC(NULL,screen);if(font)DeleteObject(font);
 return ok;
}

static int heading_text_width(const HeaderSnapshot *h,const char *label,int *width) {
 short initial=0,mono=0,last=0,style=0;unsigned short flags=0;unsigned i=0,len=(unsigned)strlen(label);int total=0;
 if(h->font_measure_kind==2){static const char *labels[]={"File","View","Help"};for(i=0;i<3;i++)if(!strcmp(labels[i],label)){if(h->gdi_widths[i]<(LONG)len||h->gdi_widths[i]>160)return 0;*width=h->gdi_widths[i];return 1;}return 0;}
 memcpy(&style,h->font_data+0x12,2);memcpy(&initial,h->font_data+0x14,2);memcpy(&mono,h->font_data+0x1c,2);memcpy(&last,h->font_data+0x1e,2);memcpy(&flags,h->font_data+0x20,2);
 if(!len||len>63||!(flags&4)||!(flags&8)||(flags&0x10)||(style&2))return 0;
 if(mono>0&&(flags&8)){total=(int)(len-1)*mono+last;}
 else{
  if(!(flags&2)||(flags&1)||!h->widths_pointer)return 0;
  total=initial>0?1:0;
  if(h->bearing_pointer){unsigned c=(BYTE)label[0];if(h->widths[c]<0)return 0;total+=h->bearings[c];i=1;}
  for(;i<len;i++){unsigned c=(BYTE)label[i];if(c>=128||h->widths[c]<0)return 0;total+=h->widths[c];}
 }
 if(total<=0||total>160)return 0;*width=total;return 1;
}
static int inspect_heading(const Panel *p,HeaderSnapshot *h) {
 FocusRecord main;HANDLE saved_process=focus_process;DWORD error=0,v=0,bar_base=0,list=0,menus[3]={0},font_table=0,font_count=0,font_base=0,item=0;
 DWORD ids[4]={0},callbacks[4]={0};const char *item_labels[4]={0};unsigned count=0,selected=0,i;int ok=0,x=0;BYTE marker=0,header[41];short coordinates[4];
 static const DWORD top_ids[]={2,4,9};static const char *labels[]={"File","View","Help"};
 focus_process=NULL;ZeroMemory(h,sizeof(*h));h->hwnd=main_hwnd;h->stage=1;
 menu_reason="menu_identity_unconfirmed";menu_detail="Menu bar could not be bound to the reviewed View or Help heading.";
 if(!menu_expected_items(p,&count,&selected,ids,callbacks,item_labels)||!original_state_ok||!resource_ok||!runtime_ok||!loaded_cvi_base)goto done;
 h->selected_index=p->menu_id==4?1:2;
 focus_process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);if(!focus_process)goto done;
 if(!observe_main_focus(&main)||!main.valid)goto done;
 h->stage=2;
 if(!focus_read_word(main.wrapper_base+0xec,&h->public_bar_handle,&error)||!focus_read_word(h->public_bar_handle,&bar_base,&error)||!readable_base(bar_base)||!focus_read_word(bar_base,&v,&error)||v!=0xeb15u)goto done;
 if(!focus_read_word(bar_base+0x4c,&list,&error)||!menu_list_entries(list,menus,3,&error)||!focus_read_word(bar_base+0x44,&h->native_bar_handle,&error)||!focus_read_word(h->native_bar_handle,&h->native_bar_base,&error)||!readable_base(h->native_bar_base))goto done;
 for(i=0;i<3;i++){
  DWORD b=0;
  h->public_menu_handles[i]=menus[i];
  if(!focus_read_word(menus[i],&b,&error)||!readable_base(b)||!focus_read_word(b,&v,&error)||v!=0xeb16u||!focus_read_word(b+0x28,&h->public_menu_ids[i],&error)||h->public_menu_ids[i]!=top_ids[i]||!focus_read_word(b+0x9c,&v,&error)||v!=h->public_bar_handle||!focus_read_word(b+0x98,&h->native_menu_handles[i],&error)||!readable_base(h->native_menu_handles[i]))goto done;
 }
 h->stage=3;
 if(!focus_read_word(h->native_bar_base,&v,&error)||v!=loaded_cvi_base+0x9f664u||!focus_read_word(h->native_bar_base+0x2c,&v,&error)||v!=3||!focus_read_word(h->native_bar_base+0x44,&v,&error)||v!=1||!focus_read_word(h->native_bar_base+0x30,&v,&error)||v||!menu_read_bytes(h->native_bar_base+0x5a,&marker,1,&error)||marker!=1)goto done;
 if(!GetClientRect(main_hwnd,&h->client_rect)||!ClientToScreen(main_hwnd,&h->client_origin)||!menu_read_bytes(h->native_bar_base+0xc,coordinates,sizeof(coordinates),&error))goto done;
 h->bar_rect.top=coordinates[0];h->bar_rect.left=coordinates[1];h->bar_rect.bottom=coordinates[2];h->bar_rect.right=coordinates[3];
 h->stage=4;menu_reason="menu_geometry_invalid";menu_detail="The actual menu-bar bounds or initialized font metrics are not supported.";
 if(h->client_rect.left||h->client_rect.top||h->client_rect.right!=895||h->client_rect.bottom!=550||h->bar_rect.left<0||h->bar_rect.top<0||(h->bar_rect.right!=h->client_rect.right&&h->bar_rect.right!=4096)||h->bar_rect.bottom>40||h->bar_rect.right<=h->bar_rect.left||h->bar_rect.bottom-h->bar_rect.top<8)goto done;
 if(!focus_read_word(h->native_bar_base+0x18,&h->font_index,&error)||!focus_read_word(loaded_cvi_base+0x20b148u,&font_table,&error)||!focus_read_word(loaded_cvi_base+0x20b14cu,&font_count,&error)||!font_count||font_count>65536||h->font_index>=font_count||!focus_read_word(font_table,&font_base,&error)||!readable_base(font_base))goto done;
 h->font_base=font_base+h->font_index*64u;
 if(!menu_read_bytes(h->font_base,h->font_data,sizeof(h->font_data),&error))goto done;
 memcpy(&v,h->font_data+4,4);if(!v||v>0x7fffffffu)goto done;
 memcpy(&h->widths_pointer,h->font_data+0x24,4);memcpy(&h->bearing_pointer,h->font_data+0x28,4);
 if(h->widths_pointer&&!menu_read_bytes(h->widths_pointer,h->widths,sizeof(h->widths),&error))goto done;
 if(h->bearing_pointer&&!menu_read_bytes(h->bearing_pointer,h->bearings,sizeof(h->bearings),&error))goto done;
 if(!menu_read_bytes(loaded_cvi_base+0x26a03cu,&h->padding,sizeof(h->padding),&error)||h->padding<=0||h->padding>64)goto done;
 {unsigned short flags=0;short mono=0;memcpy(&flags,h->font_data+0x20,2);memcpy(&mono,h->font_data+0x1c,2);
  if((flags&0x10)||((flags&8)&&mono<=0&&(flags&2)&&(flags&1))){if(!heading_gdi_widths(h))goto done;}else h->font_measure_kind=1;
 }
 h->stage=5;menu_reason="menu_identity_unconfirmed";menu_detail="Menu-bar labels, native submenu bindings or enabled state differs from the reviewed menu.";
 if(!menu_read_bytes(h->native_bar_base+0x5e,&marker,1,&error)||marker>63)goto done;
 item=h->native_bar_base+0x5e +(((unsigned)marker+4u)&~3u);x=h->bar_rect.left;
 for(i=0;i<3;i++){
  DWORD submenu=0,separator=0,b=0;short payload=0;unsigned len;int width=0;
  h->native_item_addresses[i]=item;
  if(!menu_read_bytes(item,header,sizeof(header),&error))goto done;
  memcpy(&submenu,header,4);memcpy(&payload,header+0x1a,2);memcpy(&separator,header+0x24,4);len=header[0x28];
  if(submenu!=h->native_menu_handles[i]||header[0x1e]!=1||header[0x1f]||separator||!len||len>=sizeof(h->labels[i])||payload<(int)((len+4u)&~3u)||payload>256)goto done;
  if(!focus_read_word(submenu,&b,&error)||!readable_base(b)||!focus_read_word(b+0x2c,&v,&error)||!v||v>4)goto done;
  if(!menu_read_bytes(item+0x29,h->labels[i],len,&error)||strlen(labels[i])!=len||memcmp(h->labels[i],labels[i],len)||!heading_text_width(h,h->labels[i],&width))goto done;
  width+=h->padding;/* CVI retains right=4096 after menu tracking; its hit-test replaces that
   * sentinel with the final heading edge. Every derived heading still must
   * fit the real main client; never treat the sentinel as a clickable area. */
  if(width<8||width>224||x+width>h->bar_rect.right||x+width>h->client_rect.right)goto done;
  h->heading_rects[i]=h->bar_rect;h->heading_rects[i].left=x;h->heading_rects[i].right=x+width;x+=width;
  item+=0x28u+((unsigned)(payload+3)&~3u);
 }
 h->hit.x=h->client_origin.x+(h->heading_rects[h->selected_index].left+h->heading_rects[h->selected_index].right)/2;
 h->hit.y=h->client_origin.y+(h->bar_rect.top+h->bar_rect.bottom)/2;
 if(h->hit.x<0||h->hit.y<0||h->hit.x>=GetSystemMetrics(SM_CXSCREEN)||h->hit.y>=GetSystemMetrics(SM_CYSCREEN))goto done;
 h->stage=100;ok=1;menu_reason="";menu_detail="";
 done:h->read_error=error;if(focus_process)CloseHandle(focus_process);focus_process=saved_process;return ok;
}
static int heading_observation(const HeaderSnapshot *h,int ok,const char *phase) {
 char name[64];FILE *f;unsigned i;
 _snprintf(name,sizeof(name),"heading-layout-%03d.json",++menu_serial);f=openout(name,"wb");if(!f)return 0;
 fprintf(f,"{\"read_only\":true,\"ok\":%s,\"phase\":",ok?"true":"false");js(f,phase);fputs(",\"reason\":",f);js(f,menu_reason);fputs(",\"detail\":",f);js(f,menu_detail);
 fprintf(f,",\"stage\":%u,\"read_error\":%lu,\"hwnd\":%lu,\"public_bar_handle\":%lu,\"native_bar_handle\":%lu,\"native_bar_base\":%lu,\"font_index\":%lu,\"font_base\":%lu,\"widths_pointer\":%lu,\"bearing_pointer\":%lu,\"padding\":%d,\"selected_index\":%u,\"bar_rect_client\":[%ld,%ld,%ld,%ld],\"client_origin_screen\":[%ld,%ld],\"hit_screen\":[%ld,%ld]",h->stage,(unsigned long)h->read_error,(unsigned long)(uintptr_t)h->hwnd,(unsigned long)h->public_bar_handle,(unsigned long)h->native_bar_handle,(unsigned long)h->native_bar_base,(unsigned long)h->font_index,(unsigned long)h->font_base,(unsigned long)h->widths_pointer,(unsigned long)h->bearing_pointer,h->padding,h->selected_index,h->bar_rect.left,h->bar_rect.top,h->bar_rect.right,h->bar_rect.bottom,h->client_origin.x,h->client_origin.y,h->hit.x,h->hit.y);
 fprintf(f,",\"font_measurement\":%lu,\"gdi_widths\":[%ld,%ld,%ld],\"font_metrics\":[%ld,%ld,%ld,%ld],\"runtime_modes\":[%lu,%lu,%lu],\"runtime_platform\":%lu,\"font_logfont_hex\":\"",(unsigned long)h->font_measure_kind,h->gdi_widths[0],h->gdi_widths[1],h->gdi_widths[2],h->font_metrics[0],h->font_metrics[1],h->font_metrics[2],h->font_metrics[3],(unsigned long)h->runtime_modes[0],(unsigned long)h->runtime_modes[1],(unsigned long)h->runtime_modes[2],(unsigned long)h->runtime_platform);
 for(i=0;i<sizeof(h->font_logfont);i++)fprintf(f,"%02x",h->font_logfont[i]);fputs("\",\"items\":[",f);
 for(i=0;i<3;i++){if(i)fputc(',',f);fprintf(f,"{\"public_handle\":%lu,\"public_id\":%lu,\"native_submenu_handle\":%lu,\"native_item_address\":%lu,\"rect_client\":[%ld,%ld,%ld,%ld],\"label\":",(unsigned long)h->public_menu_handles[i],(unsigned long)h->public_menu_ids[i],(unsigned long)h->native_menu_handles[i],(unsigned long)h->native_item_addresses[i],h->heading_rects[i].left,h->heading_rects[i].top,h->heading_rects[i].right,h->heading_rects[i].bottom);js(f,h->labels[i]);fputc('}',f);}
 if(fputs("]}\n",f)<0){fclose(f);return 0;}return fclose(f)==0;
}
static int observed_heading(int freeze) {
 HeaderSnapshot current;
 if(!inspect_heading(action_panel_spec,&current)){heading_observation(&current,0,"rejected");return 0;}
 if(!freeze&&(!heading_frozen||memcmp(&current,&heading_snapshot,sizeof(current)))){menu_reason="menu_geometry_invalid";menu_detail="Menu-bar identity, font metrics, geometry or HWND changed before input.";heading_observation(&current,0,"changed");return 0;}
 if(freeze){heading_snapshot=current;heading_frozen=1;if(!heading_observation(&current,1,"selected")){menu_reason="evidence_write_failed";menu_detail="Could not save verified menu-heading layout evidence.";return 0;}}
 return 1;
}

static int inspect_popup(HWND h,const Panel *p,MenuSnapshot *m) {
 FocusRecord main;DWORD error=0,v=0,bar_base=0,list=0,menus[3]={0},menu_base=0,items[4]={0};
 DWORD expected_ids[4]={0},expected_callbacks[4]={0},native=0,title_len=0,item=0;const char *labels[4]={0};
 unsigned n=0,selected=0,i,found=0;int ok=0;BYTE header[41],length=0;short coordinates[4];HANDLE saved_process=focus_process;
 static const DWORD top_ids[]={2,4,9};
 focus_process=NULL;ZeroMemory(m,sizeof(*m));ZeroMemory(&main,sizeof(main));m->hwnd=h;m->stage=1;
 menu_reason="menu_identity_unconfirmed";menu_detail="Read-only CVI menu identity could not be bound to the allowed original menu.";
 if(!p||!menu_expected_items(p,&n,&selected,expected_ids,expected_callbacks,labels))goto done;
 m->item_count=n;m->selected_index=selected;m->public_menu_id=p->menu_id;
 if(!original_state_ok||!resource_ok||!runtime_ok||!loaded_cvi_base)goto done;
 focus_process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);if(!focus_process)goto done;
 m->stage=2;
 if(!observe_main_focus(&main)||!main.valid)goto done;
 if(!focus_read_word(main.wrapper_base+0xec,&m->public_bar_handle,&error)||!focus_read_word(m->public_bar_handle,&bar_base,&error)||!readable_base(bar_base))goto done;
 if(!focus_read_word(bar_base,&v,&error)||v!=0xeb15u||!focus_read_word(bar_base+0x4c,&list,&error)||!menu_list_entries(list,menus,3,&error))goto done;
 m->stage=3;
 for(i=0;i<3;i++){
  DWORD b=0,type=0,id=0,parent=0;
  if(!focus_read_word(menus[i],&b,&error)||!readable_base(b)||!focus_read_word(b,&type,&error)||type!=0xeb16u||!focus_read_word(b+0x28,&id,&error)||id!=top_ids[i]||!focus_read_word(b+0x9c,&parent,&error)||parent!=m->public_bar_handle)goto done;
  if(id==p->menu_id){m->public_menu_handle=menus[i];menu_base=b;found++;}
 }
 if(found!=1||!focus_read_word(menu_base+0x98,&native,&error))goto done;
 m->stage=4;
 if(!focus_read_word(menu_base+0xb0,&list,&error)||!menu_list_entries(list,items,n,&error))goto done;
 for(i=0;i<n;i++){
  DWORD b=0,type=0,parent=0;
  m->public_item_handles[i]=items[i];
  if(!focus_read_word(items[i],&b,&error)||!readable_base(b)||!focus_read_word(b,&type,&error)||type!=0xeb18u||!focus_read_word(b+0x9c,&parent,&error)||parent!=m->public_menu_handle||!focus_read_word(b+0x28,&m->public_item_ids[i],&error)||m->public_item_ids[i]!=expected_ids[i]||!focus_read_word(b+0xa0,&v,&error)||v!=m->public_bar_handle||!focus_read_word(b+0x98,&v,&error)||v||!focus_read_word(b+0x3c,&m->callbacks[i],&error)||m->callbacks[i]!=expected_callbacks[i])goto done;
 }
 m->stage=5;m->window_handle=(DWORD)GetWindowLongA(h,0);
 if(!focus_read_word(m->window_handle,&m->window_base,&error)||!readable_base(m->window_base))goto done;
 if(!focus_read_word(m->window_base+0x58,&v,&error)||v!=(DWORD)(uintptr_t)h||!focus_read_word(m->window_base+0x2c,&v,&error)||v!=loaded_cvi_base+0x9f664u||!focus_read_word(m->window_base+0x50,&m->menu_handle,&error)||m->menu_handle!=native)goto done;
 if(!focus_read_word(m->menu_handle,&m->menu_base,&error)||!readable_base(m->menu_base)||!focus_read_word(m->menu_base,&v,&error)||v!=loaded_cvi_base+0x9f664u||!focus_read_word(m->menu_base+0x28,&v,&error)||v!=m->window_handle)goto done;
 m->stage=6;
 if(!focus_read_word(m->menu_base+0x44,&v,&error)||v!=1||!focus_read_word(m->menu_base+0x2c,&v,&error)||v!=n||!focus_read_word(m->menu_base+0x20,&m->row_height,&error)||!focus_read_word(m->menu_base+0x4c,&m->last_visible,&error)||!focus_read_word(m->menu_base+0x50,&m->first_visible,&error))goto done;
 if(!GetWindowRect(h,&m->window_rect)||!GetClientRect(h,&m->client_rect)||!ClientToScreen(h,&m->client_origin)||!menu_read_bytes(m->menu_base+0xc,coordinates,sizeof(coordinates),&error))goto done;
 m->native_rect.top=coordinates[0];m->native_rect.left=coordinates[1];m->native_rect.bottom=coordinates[2];m->native_rect.right=coordinates[3];
 m->stage=7;menu_reason="menu_geometry_invalid";menu_detail="Native menu rows, scrolling state and Windows client bounds do not agree.";
 if(m->row_height<8||m->row_height>64||m->first_visible!=1||m->last_visible!=n||m->client_rect.left||m->client_rect.top||m->client_rect.right<40||m->client_rect.right>800||m->client_rect.bottom!=(LONG)(n*m->row_height)||memcmp(&m->client_rect,&m->native_rect,sizeof(RECT)))goto done;
 if(m->window_rect.left<0||m->window_rect.top<0||m->window_rect.right>GetSystemMetrics(SM_CXSCREEN)||m->window_rect.bottom>GetSystemMetrics(SM_CYSCREEN)||m->client_origin.x<m->window_rect.left||m->client_origin.y<m->window_rect.top||m->client_origin.x+m->client_rect.right>m->window_rect.right||m->client_origin.y+m->client_rect.bottom>m->window_rect.bottom)goto done;
 m->stage=8;menu_reason="menu_identity_unconfirmed";menu_detail="Native menu labels, item state or public callback identity differs from the allowlist.";
 if(!menu_read_bytes(m->menu_base+0x5e,&length,1,&error)||length>63)goto done;title_len=length;
 item=m->menu_base+0x5e +((title_len+4u)&~3u);
 for(i=0;i<n;i++){
  short payload=0;DWORD submenu=0,separator=0;unsigned text_size;
  m->native_item_addresses[i]=item;
  if(!menu_read_bytes(item,header,sizeof(header),&error))goto done;
  memcpy(&submenu,header,4);memcpy(&payload,header+0x1a,2);memcpy(&separator,header+0x24,4);text_size=header[0x28];
  m->native_submenus[i]=submenu;m->native_separator[i]=separator;m->enabled[i]=header[0x1e];m->checked[i]=header[0x1f];
  if(submenu||separator||m->checked[i]||m->enabled[i]>1||!text_size||text_size>=sizeof(m->labels[i])||payload<(int)((text_size+4u)&~3u)||payload>256)goto done;
  if(!menu_read_bytes(item+0x29,m->labels[i],text_size,&error)||strlen(labels[i])!=text_size||memcmp(m->labels[i],labels[i],text_size))goto done;
  if(i==selected&&m->enabled[i]!=1)goto done;
  item+=0x28u+((unsigned)(payload+3)&~3u);
 }
 m->stage=9;m->item_rect=m->client_rect;m->item_rect.top=(LONG)(selected*m->row_height);m->item_rect.bottom=m->item_rect.top+(LONG)m->row_height;
 m->item_rect.left+=m->client_origin.x;m->item_rect.right+=m->client_origin.x;m->item_rect.top+=m->client_origin.y;m->item_rect.bottom+=m->client_origin.y;
 m->hit.x=m->item_rect.left+(m->item_rect.right-m->item_rect.left)/2;m->hit.y=m->item_rect.top+(m->item_rect.bottom-m->item_rect.top)/2;
 if(!PtInRect(&m->window_rect,m->hit))goto done;
 m->stage=100;menu_reason="";menu_detail="";ok=1;
 done:
 m->read_error=error;
 if(focus_process)CloseHandle(focus_process);focus_process=saved_process;
 return ok;
}
static int menu_observation(const MenuSnapshot *m,int ok,const char *phase) {
 char name[64];FILE *f;unsigned i;
 _snprintf(name,sizeof(name),"menu-layout-%03d.json",++menu_serial);f=openout(name,"wb");if(!f)return 0;
 fprintf(f,"{\"read_only\":true,\"ok\":%s,\"phase\":",ok?"true":"false");js(f,phase);
 fputs(",\"reason\":",f);js(f,menu_reason);fputs(",\"detail\":",f);js(f,menu_detail);
 fprintf(f,",\"stage\":%u,\"read_error\":%lu,\"hwnd\":%lu,\"window_handle\":%lu,\"window_base\":%lu,\"native_menu_handle\":%lu,\"native_menu_base\":%lu,\"public_bar_handle\":%lu,\"public_menu_handle\":%lu,\"public_menu_id\":%lu,\"item_count\":%u,\"row_height\":%u,\"first_visible\":%u,\"last_visible\":%u,\"selected_index\":%u",m->stage,(unsigned long)m->read_error,(unsigned long)(uintptr_t)m->hwnd,(unsigned long)m->window_handle,(unsigned long)m->window_base,(unsigned long)m->menu_handle,(unsigned long)m->menu_base,(unsigned long)m->public_bar_handle,(unsigned long)m->public_menu_handle,(unsigned long)m->public_menu_id,m->item_count,m->row_height,m->first_visible,m->last_visible,m->selected_index);
 fprintf(f,",\"window_rect\":[%ld,%ld,%ld,%ld],\"client_rect\":[%ld,%ld,%ld,%ld],\"native_rect\":[%ld,%ld,%ld,%ld],\"client_origin_screen\":[%ld,%ld],\"item_rect_screen\":[%ld,%ld,%ld,%ld],\"hit_screen\":[%ld,%ld],\"items\":[",m->window_rect.left,m->window_rect.top,m->window_rect.right,m->window_rect.bottom,m->client_rect.left,m->client_rect.top,m->client_rect.right,m->client_rect.bottom,m->native_rect.left,m->native_rect.top,m->native_rect.right,m->native_rect.bottom,m->client_origin.x,m->client_origin.y,m->item_rect.left,m->item_rect.top,m->item_rect.right,m->item_rect.bottom,m->hit.x,m->hit.y);
 for(i=0;i<m->item_count&&i<4;i++){
  if(i)fputc(',',f);fprintf(f,"{\"public_handle\":%lu,\"public_id\":%lu,\"callback\":%lu,\"native_address\":%lu,\"submenu\":%lu,\"separator\":%lu,\"enabled\":%u,\"checked\":%u,\"label\":",(unsigned long)m->public_item_handles[i],(unsigned long)m->public_item_ids[i],(unsigned long)m->callbacks[i],(unsigned long)m->native_item_addresses[i],(unsigned long)m->native_submenus[i],(unsigned long)m->native_separator[i],m->enabled[i],m->checked[i]);js(f,m->labels[i]);fputc('}',f);
 }
 if(fputs("]}\n",f)<0){fclose(f);return 0;}return fclose(f)==0;
}

static int guard_phase,guard_extra_windows,guard_edit_children;static HWND guard_owned;
static const char *guard_window_reason;
static BOOL CALLBACK context_child_cb(HWND h,LPARAM param) {
 WCHAR cls[128];(void)param;if(!IsWindowVisible(h))return TRUE;
 GetClassNameW(h,cls,128);
 if(!_wcsicmp(cls,L"Edit")||!_wcsicmp(cls,L"RichEdit")||!_wcsicmp(cls,L"RichEdit20A")||!_wcsicmp(cls,L"RichEdit20W")||!_wcsicmp(cls,L"ComboBox")||!_wcsicmp(cls,L"ComboLBox"))guard_edit_children++;
 return TRUE;
}
static BOOL CALLBACK context_window_cb(HWND h,LPARAM param) {
 DWORD pid=0;WCHAR cls[128];RECT r;(void)param;GetWindowThreadProcessId(h,&pid);
 if(pid!=original_pid||!IsWindowVisible(h)||h==main_hwnd)return TRUE;
 GetClassNameW(h,cls,128);GetWindowRect(h,&r);
 if(!_wcsicmp(cls,L"CVIRTLVFrame4194304")&&r.right<=0&&r.bottom<=0)return TRUE;
 if(guard_phase==2&&h==guard_owned)return TRUE;
 if(!_wcsicmp(cls,L"CVIRTLVMenuWnd4194304")||!_wcsicmp(cls,L"#32768")){
  if(guard_phase==1&&h==popup_hwnd)return TRUE;
  guard_window_reason="original_popup_open";
 }else if(!guard_window_reason)guard_window_reason="initial_auxiliary_open";
 guard_extra_windows++;return TRUE;
}
static int any_held_input(void) {int key;for(key=1;key<256;key++)if(GetAsyncKeyState(key)&0x8000)return 1;return 0;}
/* phase0=clean main, phase1=our exact menu popup, phase2=our freshly opened panel.
 * No foreground change, keyboard input or original runtime call occurs here. */
static int context_guard(const char *label,int phase,HWND owned) {
 FocusRecord focus;GUITHREADINFO gui;LASTINPUTINFO last;DWORD optout=0,access=0,hold=0,error=0;
 int ok=0;char leaf[64],timestamp[40];FILE *f;HWND caret=NULL,winfocus=NULL;
 ZeroMemory(&focus,sizeof(focus));ZeroMemory(&gui,sizeof(gui));ZeroMemory(&last,sizeof(last));
 gui.cbSize=sizeof(gui);last.cbSize=sizeof(last);context_reason="";context_input_valid=0;
 if(cancelled()){context_reason="external_input_detected";goto done;}
 if(!original_state_ok||!resource_ok||!runtime_ok||!find_main()){context_reason=warning_count?"connection_warning":"identity_mismatch";goto done;}
 focus_process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);
 if(!focus_process){context_reason="identity_mismatch";goto done;}
 if(!focus_read_word(0x4141d0u,&optout,&error)||!focus_read_word(0x416decu,&access,&error)||!focus_read_word(0x414a9cu,&hold,&error)){context_reason="identity_mismatch";goto done;}
 if(optout!=1){context_reason="optout_off";goto done;}
 if(access!=(DWORD)action_start_access||(initial_access>=0&&access!=(DWORD)initial_access)){context_reason="editable_or_unknown_focus";goto done;}
 if(hold){context_reason="connection_warning";goto done;}
 if(any_held_input()){context_reason="external_input_detected";goto done;}
 if(!GetLastInputInfo(&last)){context_reason="external_input_detected";goto done;}
 if(phase!=0&&(!own_input_valid||last.dwTime!=own_input_tick)){context_reason="external_input_detected";goto done;}
 if(phase==1&&!observed_popup(0)){context_reason="original_popup_open";goto done;}
 guard_phase=phase;guard_owned=owned;guard_extra_windows=guard_edit_children=0;guard_window_reason=NULL;
 EnumWindows(context_window_cb,0);
 if(guard_extra_windows){context_reason=guard_window_reason?guard_window_reason:"initial_auxiliary_open";goto done;}
 EnumChildWindows(main_hwnd,context_child_cb,0);
 if(guard_edit_children){context_reason="editable_or_unknown_focus";goto done;}
 if(!GetGUIThreadInfo(GetWindowThreadProcessId(main_hwnd,NULL),&gui)){context_reason="editable_or_unknown_focus";goto done;}
 caret=gui.hwndCaret;winfocus=gui.hwndFocus;
 if(caret&&(phase!=2||(caret!=owned&&!IsChild(owned,caret)))){context_reason="editable_or_unknown_focus";goto done;}
 if(phase!=1&&(gui.flags&(GUI_INMENUMODE|GUI_POPUPMENUMODE|GUI_SYSTEMMENUMODE))){context_reason="original_popup_open";goto done;}
 if(gui.flags&GUI_INMOVESIZE){context_reason="external_input_detected";goto done;}
 if(winfocus&&winfocus!=main_hwnd&&(phase!=2||(winfocus!=owned&&!IsChild(owned,winfocus)))){context_reason="editable_or_unknown_focus";goto done;}
 if(!observe_main_focus(&focus)||!focus_policy(focus.valid,focus.active,focus.node,focus.kind,focus.public_id,focus.matches)){context_reason="editable_or_unknown_focus";goto done;}
 if(phase==2&&(!owned||!IsWindowVisible(owned))){context_reason="initial_auxiliary_open";goto done;}
 ok=1;context_input_tick=last.dwTime;context_input_valid=1;
 done:
 if(focus_process){CloseHandle(focus_process);focus_process=NULL;}
 _snprintf(leaf,sizeof(leaf),"context-%03d.json",++context_serial);utc(timestamp,sizeof(timestamp));f=openout(leaf,"wb");
 if(f){
  fputs("{\"utc_guest_clock\":",f);js(f,timestamp);fputs(",\"label\":",f);js(f,label);fputs(",\"context_reason\":",f);js(f,context_reason);
  fprintf(f,",\"ok\":%s,\"mouse_only\":true,\"phase\":%d,\"main_hwnd\":%lu,\"owned_hwnd\":%lu,\"focus_hwnd\":%lu,\"caret_hwnd\":%lu,\"last_input_tick\":%lu,\"own_mouse_up_tick\":%lu,\"access_level\":%lu,\"window_handle\":%lu,\"panel_handle\":%lu,\"wrapper_handle\":%lu,\"wrapper_id\":%lu,\"active\":%lu,\"selection_node\":%lu,\"selection_kind\":%lu,\"selection_value\":%lu,\"native_id\":%lu,\"public_id\":%lu,\"matches\":%d,\"focus_valid\":%s,\"read_error\":%lu}\n",ok?"true":"false",phase,(unsigned long)(uintptr_t)main_hwnd,(unsigned long)(uintptr_t)owned,(unsigned long)(uintptr_t)winfocus,(unsigned long)(uintptr_t)caret,(unsigned long)last.dwTime,(unsigned long)own_input_tick,(unsigned long)access,(unsigned long)focus.window_handle,(unsigned long)focus.panel_handle,(unsigned long)focus.wrapper_handle,(unsigned long)focus.wrapper_id,(unsigned long)focus.active,(unsigned long)focus.node,(unsigned long)focus.kind,(unsigned long)focus.selector,(unsigned long)focus.native_id,(unsigned long)focus.public_id,focus.matches,focus.valid?"true":"false",(unsigned long)(focus.error?focus.error:error));fclose(f);
 }else{ok=0;context_reason="evidence_write_failed";}
 if(!ok)event(label,"context_blocked",context_reason,97);
 return ok;
}
static int hidden_target_guard(const Panel *p,HWND expected) {
 DWORD w=0,wb=0,panel=0,pb=0,wrapper=0,hb=0,v=0,type=0,id=0,expected_id=0,active=0,secondary=0,error=0;
 HWND target=NULL;int ok=0;char leaf[64];FILE *f;
 if(!find_hidden_panel(p)){context_reason="initial_auxiliary_open";goto done;}
 target=panel_hwnd;if(expected&&target!=expected){context_reason="identity_mismatch";goto done;}
 focus_process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);
 if(!focus_process)goto blocked;
 w=(DWORD)GetWindowLongA(target,0);
 if(!focus_read_word(w,&wb,&error)||!readable_base(wb)||!focus_read_word(wb+0x58,&v,&error)||v!=(DWORD)(uintptr_t)target)goto blocked;
 if(!focus_read_word(wb+0x2c,&v,&error)||v!=loaded_cvi_base+0x1aebb1u||!focus_read_word(wb+0x50,&panel,&error)||!focus_read_word(panel,&pb,&error)||!readable_base(pb))goto blocked;
 if(!focus_read_word(pb+0x5c,&v,&error)||v!=w||!focus_read_word(pb+0x78,&v,&error)||v!=loaded_cvi_base+0x16aaaeu)goto blocked;
 if(!focus_read_word(pb+0x74,&wrapper,&error)||!focus_read_word(wrapper,&hb,&error)||!readable_base(hb))goto blocked;
 if(!focus_read_word(hb,&type,&error)||type!=0xeb13u||!focus_read_word(hb+0xa0,&v,&error)||v!=panel)goto blocked;
 if(!focus_read_word(hb+0x28,&id,&error)||!focus_read_word(p->panel_global,&expected_id,&error)||id!=expected_id)goto blocked;
 if(!focus_read_word(pb+0x44,&active,&error)||!focus_read_word(pb+0x48,&secondary,&error)||active||secondary)goto blocked;
 ok=1;action_hidden_hwnd=target;goto done;
 blocked:context_reason="editable_or_unknown_focus";
 done:
 if(focus_process){CloseHandle(focus_process);focus_process=NULL;}
 _snprintf(leaf,sizeof(leaf),"target-context-%03d.json",++context_serial);f=openout(leaf,"wb");
 if(f){fputs("{\"mode\":",f);js(f,p->mode);fputs(",\"context_reason\":",f);js(f,ok?"":context_reason);
  fprintf(f,",\"ok\":%s,\"read_only\":true,\"hidden_hwnd\":%lu,\"panel_global\":%lu,\"expected_panel_id\":%lu,\"wrapper_id\":%lu,\"panel_handle\":%lu,\"active_44\":%lu,\"active_48\":%lu,\"win32_error\":%lu}\n",ok?"true":"false",(unsigned long)(uintptr_t)target,(unsigned long)p->panel_global,(unsigned long)expected_id,(unsigned long)id,(unsigned long)panel,(unsigned long)active,(unsigned long)secondary,(unsigned long)error);fclose(f);
 }else{ok=0;context_reason="evidence_write_failed";}
 if(!ok)event(p->mode,"hidden_target_blocked",context_reason,97);return ok;
}
static int recheck_hidden_target(void) {return action_panel_spec&&action_hidden_hwnd&&hidden_target_guard(action_panel_spec,action_hidden_hwnd);}
static int menu_target_unchanged(HWND expected,POINT point,int allow_menu) {
 DWORD pid=0;RECT client;POINT origin={0,0};WCHAR title[512],cls[256];HWND under;
 GetWindowThreadProcessId(expected,&pid);
 if(expected!=main_hwnd||pid!=original_pid||!IsWindowVisible(expected)||!IsWindowEnabled(expected)||GetForegroundWindow()!=expected)return 0;
 window_text(expected,title,512);GetClassNameW(expected,cls,256);
 if(_wcsicmp(title,L"Spitfire")||_wcsicmp(cls,L"CVIRTLVDChild4194304")||!GetClientRect(expected,&client)||client.left!=0||client.top!=0||client.right!=895||client.bottom!=550)return 0;
 if(!ClientToScreen(expected,&origin)||origin.x!=action_main_origin.x||origin.y!=action_main_origin.y)return 0;
 if(allow_menu){if(!observed_popup(0)||point.x!=menu_snapshot.hit.x||point.y!=menu_snapshot.hit.y)return 0;}
 else if(!observed_heading(0)||point.x!=heading_snapshot.hit.x||point.y!=heading_snapshot.hit.y)return 0;
 under=WindowFromPoint(point);
 /* The reviewed CVI popup is disabled to Win32 hit testing, which can return
  * its underlying main window. Other same-PID auxiliary windows are rejected. */
 if(under!=expected&&!IsChild(expected,under)&&(!allow_menu||under!=popup_hwnd))return 0;
 return !cancelled()&&!modifiers_down();
}
static int show_panel(const Panel *p) {
 POINT menu={0,0},item={0,0},origin={0,0};HWND target;
 if(!action_guard(p->mode))return 82;
 if(!context_guard("before_main_foreground",0,NULL))return 97;
 if(find_panel(p)||panel_count){context_reason="initial_auxiliary_open";return 97;}
 action_panel_spec=p;action_hidden_hwnd=NULL;menu_frozen=heading_frozen=0;popup_hwnd=NULL;if(!hidden_target_guard(p,NULL))return 97;
 if(!activate_exact(main_hwnd)){event(p->mode,"blocked","Exact main panel cannot be foregrounded",84);return 84;}
 if(!ClientToScreen(main_hwnd,&origin))return 84;action_main_origin=origin;
 if(!observed_heading(1)){
  if(!*failure_reason){failure_reason=*menu_reason?menu_reason:"menu_heading_unconfirmed";_snprintf(failure_detail,sizeof(failure_detail),"%s",menu_detail);failure_detail[sizeof(failure_detail)-1]=0;}
  event(p->mode,"blocked","Actual allowed menu heading could not be identified; no input sent",85);return 85;
 }
 menu=heading_snapshot.hit;
 if(!action_guard(p->mode)||!mouse_click(main_hwnd,menu,0)){event(p->mode,"blocked","Menu heading lost verified original target; no item click",85);return 85;}
 if(!wait_cancel(300))return 80;snapshot("menu-open");
 if(!action_guard(p->mode))return 82;
 if(!observed_popup(1)){
  if(!*failure_reason){failure_reason=*menu_reason?menu_reason:"menu_popup_unconfirmed";_snprintf(failure_detail,sizeof(failure_detail),"%s",menu_detail);failure_detail[sizeof(failure_detail)-1]=0;}
  event(p->mode,"blocked","Menu identity or actual item geometry could not be verified; no item click",86);return 86;
 }
 item=menu_snapshot.hit;
 if(!mouse_click(main_hwnd,item,1)){
  if(!*failure_reason&&*menu_reason){failure_reason=menu_reason;_snprintf(failure_detail,sizeof(failure_detail),"%s",menu_detail);failure_detail[sizeof(failure_detail)-1]=0;}
  event(p->mode,"blocked","Verified menu item changed or lost ownership before input",87);return 87;
 }
 event(p->mode,"opened","Selected fixed reviewed show-panel menu item",0);
 if(!wait_cancel(2000))return 80;
 if(!original_state("original-state-open.json",&current_optout,&current_access)||!find_panel(p)||panel_hwnd!=action_hidden_hwnd){
  event(p->mode,"unconfirmed","Expected auxiliary title/class/geometry not observed; no close attempted",88);return 88;
 }
 target=panel_hwnd;if(!context_guard("before_panel_evidence",2,target))return 97;snapshot("panel-open");
 if(!wait_cancel(2000))return 80;
 /* Only these exact auxiliary panels have measured close_ctrl callbacks that
  * solely HidePanel. No generic close API, no main close and no warning retry. */
 if(!runtime_ok){event(p->mode,"skipped_close","Unreviewed loaded CVI runtime; leave panel open",0);return 0;}
 if(!action_guard(p->mode)||!runtime_ok||!find_panel(p)||panel_hwnd!=target||target==main_hwnd||cancelled()||!capture_proof())return 82;
 if(!context_guard("before_auxiliary_hide",2,target))return 97;
 {LASTINPUTINFO last;ZeroMemory(&last,sizeof(last));last.cbSize=sizeof(last);if(!GetLastInputInfo(&last)||!own_input_valid||last.dwTime!=own_input_tick||any_held_input()){context_reason="external_input_detected";event(p->mode,"context_blocked",context_reason,97);return 97;}}
 if(!PostMessageW(target,WM_SYSCOMMAND,SC_CLOSE,0)){event(p->mode,"skipped_close","Reviewed auxiliary close message failed; no retry",89);return 89;}
 event(p->mode,"auxiliary_close","Exact auxiliary close_ctrl dispatches its HidePanel-only callback",p->close_control);
 if(!wait_cancel(600))return 80;
 if(IsWindowVisible(target)){event(p->mode,"unconfirmed_close","Auxiliary remains visible; no retry",90);return 90;}
 return 0;
}
static void skipped_items(void) {
 FILE *f=openout("skipped.jsonl","wb");if(!f)return;
 fputs("{\"item\":\"Original start, exit, restart, connection Warning OK\",\"reason\":\"Attach only; startup/reconnect can automatically send EMP:LBOBREAK 1\"}\n",f);
 fputs("{\"item\":\"RUN, STOP, Laser ON/OFF, HV, motor, parameter editors, temperature, sliders, mode selectors\",\"reason\":\"Device-changing controls excluded\"}\n",f);
 fputs("{\"item\":\"Empower/TCU Opt-out, fault reset, interlock/humidity/TDG overrides\",\"reason\":\"Changes device or safety state\"}\n",f);
 fputs("{\"item\":\"Escape, arbitrary shortcuts, factory/programmer modes, console, unknown buttons\",\"reason\":\"Not in reviewed display-only allowlist\"}\n",f);
 fputs("{\"item\":\"regensvc/user and access-level switching\",\"reason\":\"Keyboard routing to an active CVI ring/editor is not proven read-only; no keyboard input is implemented\"}\n",f);
 fclose(f);
}
static int driver_main(int argc,char **argv) {
 const char *mode;const Panel *panel=NULL;int preflight=0,rc=0,i,optout=-1,access=-1,ready=0;DWORD pid_before;FILE *f;char t[40];
 if(argc<3||argc>5)return 2;mode=argv[1];preflight=!strcmp(mode,"preflight");
 for(i=0;i<(int)(sizeof(panels)/sizeof(panels[0]));i++)if(!strcmp(mode,panels[i].mode))panel=&panels[i];
 if(!preflight&&!panel)return 2;
 if(!preflight&&argc!=5)return 2;if(preflight&&argc!=3)return 2;
 if(strlen(argv[2])>MAX_PATH-64)return 2;strcpy(outdir,argv[2]);
 if(!CreateDirectoryA(outdir,NULL))return 3;timeline=openout("timeline.jsonl","wb");if(!timeline)return 3;
 if(!preflight){proof_path=argv[3];stop_path=argv[4];}
 event(mode,"begin","Attach-only original UI test; helper has no network interface",0);skipped_items();
 if(!processes()){rc=4;goto done;}pid_before=original_pid;
 if(!inventory_windows()||!screenshot()){event(mode,"blocked","Initial screenshot/inventory incomplete",4);rc=4;goto done;}
 snapshot("before");
 original_state("original-state-before.json",&optout,&access);
 action_start_access=access;
 if(preflight)focus_probe();
 ready=original_state_ok&&resource_ok&&runtime_ok&&optout==1&&(access==0||access==1)&&hold_thread==0&&find_main();
 if(!ready){
  if(original_foreign)preflight_reason="identity_mismatch";
  else if(original_exact_count==0)preflight_reason="original_missing";
  else if(!original_state_ok||!resource_ok||!runtime_ok)preflight_reason="identity_mismatch";
  else if(optout!=1)preflight_reason="optout_off";
  else if(warning_count||hold_thread)preflight_reason="connection_warning";
  else preflight_reason="editable_or_unknown_focus";
  event(mode,"capture_only",preflight_reason,20);rc=20;goto done;
 }
 if(!preflight&&panel&&!strcmp(mode,"setup")&&access==0&&optout==1){
  action_skipped=1;skip_reason="disabledOptoutuser";
  event(mode,"skipped","Empower Setup is disabled by the original in user mode with Empower Opt-out ON; no input sent",0);goto done;
 }
 if(!context_guard("initial_context",0,NULL)){ready=0;preflight_reason=context_reason;rc=20;goto done;}
 if(!preflight)rc=show_panel(panel);
 if(!processes()||original_pid!=pid_before){event(mode,"blocked","Original process changed; stop subsequent actions",96);rc=96;}
 done:
 processes();snapshot("after");original_state("original-state.json",&optout,&access);utc(t,sizeof(t));
 if(rc&&!*failure_reason){failure_reason=native_failure_reason(rc);strcpy(failure_detail,"Native action stopped; see timeline and context evidence.");}
 f=openout("result.json","wb");if(f){
  fputs("{\"controller_version\":\"1.1\",\"utc_guest_clock\":",f);js(f,t);fputs(",\"mode\":",f);js(f,mode);
  fputs(",\"failure_reason\":",f);js(f,rc?failure_reason:"");fputs(",\"failure_detail\":",f);js(f,rc?failure_detail:"");
  fputs(",\"preflight_reason\":",f);js(f,preflight_reason);fputs(",\"context_reason\":",f);js(f,context_reason);fputs(",\"skip_reason\":",f);js(f,skip_reason);
  fprintf(f,",\"skipped\":%s,\"keyboard_input_implemented\":false",action_skipped?"true":"false");
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
