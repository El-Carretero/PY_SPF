/* Offline WinPcap 4.1.3 provisioner, Windows XP SP3 x86.
 * Runs the unchanged official installer only when no WinPcap files/service exist.
 * No hardware-control API, packets, registry writes, driver extraction, /S or /NCRC.
 * The installer performs its own supported installation. Unknown dialogs stop.
 */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <stdint.h>
#ifndef CALG_SHA_256
#define CALG_SHA_256 0x0000800c
#endif
typedef struct old_FILE FILE;
__declspec(dllimport) FILE * __cdecl fopen(const char*,const char*);
__declspec(dllimport) int __cdecl fclose(FILE*);
__declspec(dllimport) int __cdecl fflush(FILE*);
__declspec(dllimport) int __cdecl fprintf(FILE*,const char*,...);
__declspec(dllimport) int __cdecl fputs(const char*,FILE*);
__declspec(dllimport) int __cdecl fputc(int,FILE*);
__declspec(dllimport) LPWSTR* WINAPI CommandLineToArgvW(LPCWSTR,int*);
static FILE *logfile;
static DWORD installer_pid;
static HWND wizard, button, option;
static int window_count, option_count;
static WCHAR page[32000];
static const char expected_sha256[]="fc4623b113a1f603c0d9ad5f83130bd6de1c62b973be9892305132389c8588de";
static int contains(const WCHAR*a,const WCHAR*b){int i,j;for(i=0;a[i];i++){for(j=0;b[j]&&a[i+j]==b[j];j++){}if(!b[j])return 1;}return !*b;}
static void js(const char*s){const BYTE*p=(const BYTE*)s;fputc('"',logfile);for(;*p;p++){if(*p=='"'||*p=='\\'){fputc('\\',logfile);fputc(*p,logfile);}else if(*p<32)fprintf(logfile,"\\u%04x",*p);else fputc(*p,logfile);}fputc('"',logfile);}
static void event(const char*phase,const WCHAR*detail,int code){SYSTEMTIME t;static char u8[128000];if(!logfile)return;GetSystemTime(&t);WideCharToMultiByte(CP_UTF8,0,detail,-1,u8,sizeof(u8),NULL,NULL);fprintf(logfile,"{\"utc\":\"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ\",\"phase\":",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds);js(phase);fputs(",\"detail\":",logfile);js(u8);fprintf(logfile,",\"code\":%d}\n",code);fflush(logfile);}
static int exists(const WCHAR*p){DWORD a=GetFileAttributesW(p);if(a!=INVALID_FILE_ATTRIBUTES)return 1;return GetLastError()!=ERROR_FILE_NOT_FOUND&&GetLastError()!=ERROR_PATH_NOT_FOUND;}
static int no_registry(const WCHAR*subkey){HKEY key;LONG r=RegOpenKeyExW(HKEY_LOCAL_MACHINE,subkey,0,KEY_READ,&key);if(r==ERROR_SUCCESS){RegCloseKey(key);event("existing_registry",subkey,1);return 0;}return r==ERROR_FILE_NOT_FOUND;}
static int all_absent(void){WCHAR sys[MAX_PATH],path[MAX_PATH];const WCHAR*leaves[]={L"\\wpcap.dll",L"\\Packet.dll",L"\\drivers\\npf.sys"};SC_HANDLE scm,s;int i;DWORD err;
 if(!GetSystemDirectoryW(sys,MAX_PATH)||lstrlenW(sys)>MAX_PATH-40)return 0;
 for(i=0;i<3;i++){lstrcpyW(path,sys);lstrcatW(path,leaves[i]);if(exists(path)){event("existing_file",path,1);return 0;}}
 scm=OpenSCManagerW(NULL,NULL,SC_MANAGER_CONNECT);if(!scm)return 0;s=OpenServiceW(scm,L"npf",SERVICE_QUERY_STATUS);err=GetLastError();if(s)CloseServiceHandle(s);if(s||err!=ERROR_SERVICE_DOES_NOT_EXIST){CloseServiceHandle(scm);event("existing_service",L"npf exists or cannot be queried; no repair/downgrade allowed",(int)err);return 0;}
 s=OpenServiceW(scm,L"rpcapd",SERVICE_QUERY_STATUS);err=GetLastError();if(s)CloseServiceHandle(s);CloseServiceHandle(scm);if(s||err!=ERROR_SERVICE_DOES_NOT_EXIST){event("existing_service",L"rpcapd exists or cannot be queried; no replacement of remote capture components allowed",(int)err);return 0;}
 return no_registry(L"SOFTWARE\\WinPcap")&&no_registry(L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\WinPcapInst");
}
static HANDLE verify_file(const WCHAR*path){HCRYPTPROV p=0;HCRYPTHASH h=0;HANDLE f=INVALID_HANDLE_VALUE;BYTE buf[8192],digest[32];DWORD got,n=32;int i,ok=0;char hex[65];const char*d="0123456789abcdef";
 if(!CryptAcquireContextW(&p,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&!CryptAcquireContextW(&p,NULL,L"Microsoft Enhanced RSA and AES Cryptographic Provider (Prototype)",PROV_RSA_AES,CRYPT_VERIFYCONTEXT))goto done;
 if(!CryptCreateHash(p,CALG_SHA_256,0,0,&h))goto done;
 f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);if(f==INVALID_HANDLE_VALUE||GetFileSize(f,NULL)!=915128)goto done;
 for(;;){if(!ReadFile(f,buf,sizeof(buf),&got,NULL))goto done;if(!got)break;if(!CryptHashData(h,buf,got,0))goto done;}
 if(!CryptGetHashParam(h,HP_HASHVAL,digest,&n,0)||n!=32)goto done;for(i=0;i<32;i++){hex[2*i]=d[digest[i]>>4];hex[2*i+1]=d[digest[i]&15];}hex[64]=0;ok=lstrcmpA(hex,expected_sha256)==0;
 done:if(h)CryptDestroyHash(h);if(p)CryptReleaseContext(p,0);if(!ok&&f!=INVALID_HANDLE_VALUE){CloseHandle(f);f=INVALID_HANDLE_VALUE;}return f;
}
static void get_text(HWND h,WCHAR*b,int n){DWORD_PTR r=0;b[0]=0;SendMessageTimeoutW(h,WM_GETTEXT,n,(LPARAM)b,SMTO_BLOCK|SMTO_ABORTIFHUNG,300,&r);b[n-1]=0;}
static BOOL CALLBACK child_cb(HWND h,LPARAM x){WCHAR s[18000],cls[64];int used;(void)x;if(!IsWindowVisible(h))return TRUE;get_text(h,s,18000);GetClassNameW(h,cls,64);used=lstrlenW(page);if(*s&&used+lstrlenW(s)+2<32000){lstrcatW(page,s);lstrcatW(page,L"\n");}
 if(!lstrcmpW(cls,L"Button")&&GetDlgCtrlID(h)==IDOK&&IsWindowEnabled(h))button=h;
 if(!lstrcmpW(cls,L"Button")&&!lstrcmpW(s,L"Automatically start the WinPcap driver at boot time")){option=h;option_count++;}return TRUE;
}
static BOOL CALLBACK top_cb(HWND h,LPARAM x){DWORD pid;WCHAR cls[64],title[256];(void)x;GetWindowThreadProcessId(h,&pid);if(pid!=installer_pid||!IsWindowVisible(h))return TRUE;GetClassNameW(h,cls,64);get_text(h,title,256);if(lstrcmpW(cls,L"#32770"))return TRUE;window_count++;/* Observed official NSIS: welcome has no trailing space, license/options do. */if(!lstrcmpW(title,L"WinPcap 4.1.3 Setup")||!lstrcmpW(title,L"WinPcap 4.1.3 Setup "))wizard=h;return TRUE;}
static int inspect(void){wizard=NULL;button=NULL;option=NULL;window_count=0;option_count=0;page[0]=0;EnumWindows(top_cb,0);if(window_count!=1||!wizard||!IsWindowEnabled(wizard))return 0;EnumChildWindows(wizard,child_cb,0);return 1;}
static int click_button(const WCHAR*expected){WCHAR label[256],cls[64];DWORD pid=0;DWORD_PTR result=0;if(!button||!IsWindowEnabled(button)||!IsWindowVisible(button))return 0;GetWindowThreadProcessId(button,&pid);get_text(button,label,256);GetClassNameW(button,cls,64);if(pid!=installer_pid||lstrcmpW(cls,L"Button")||lstrcmpW(label,expected)||GetDlgCtrlID(button)!=IDOK||!IsChild(wizard,button))return 0;event("installer_button",expected,0);return SendMessageTimeoutW(button,BM_CLICK,0,0,SMTO_ABORTIFHUNG,2000,&result)!=0;}
static int has_installed_files(void){WCHAR p[MAX_PATH],s[MAX_PATH];SC_HANDLE scm,svc;int ok;GetSystemDirectoryW(s,MAX_PATH);lstrcpyW(p,s);lstrcatW(p,L"\\wpcap.dll");if(!exists(p))return 0;lstrcpyW(p,s);lstrcatW(p,L"\\Packet.dll");if(!exists(p))return 0;scm=OpenSCManagerW(NULL,NULL,SC_MANAGER_CONNECT);if(!scm)return 0;svc=OpenServiceW(scm,L"npf",SERVICE_QUERY_STATUS);ok=svc!=NULL;if(svc)CloseServiceHandle(svc);CloseServiceHandle(scm);return ok;}
static int run(int argc,WCHAR**argv){WCHAR logpath[MAX_PATH],staging[MAX_PATH],exe[MAX_PATH],cmd[MAX_PATH+8],sys[MAX_PATH],prior[32000];char loga[MAX_PATH*3];BOOL bad=FALSE;HANDLE locked=INVALID_HANDLE_VALUE;STARTUPINFOW si;PROCESS_INFORMATION pi;OSVERSIONINFOA ver;SYSTEM_INFO system;DWORD start,last_good,exitcode=999;int stage=0,inspect_only=0,rc=31;BOOL admin=FALSE;SID_IDENTIFIER_AUTHORITY auth=SECURITY_NT_AUTHORITY;PSID sid=NULL;
 if(argc!=4||((inspect_only=lstrcmpW(argv[1],L"--inspect")==0)==0&&lstrcmpW(argv[1],L"--install")))return 2;
 if(lstrlenW(argv[2])>MAX_PATH-20||lstrlenW(argv[3])>MAX_PATH-60)return 3;
 CreateDirectoryW(argv[3],NULL);lstrcpyW(logpath,argv[3]);lstrcatW(logpath,L"\\winpcap-install.jsonl");if(!WideCharToMultiByte(CP_ACP,0,logpath,-1,loga,sizeof(loga),NULL,&bad)||bad)return 4;logfile=fopen(loga,"wb");if(!logfile)return 4;
 ZeroMemory(&ver,sizeof(ver));ver.dwOSVersionInfoSize=sizeof(ver);GetVersionExA(&ver);GetNativeSystemInfo(&system);if(ver.dwPlatformId!=VER_PLATFORM_WIN32_NT||ver.dwMajorVersion!=5||ver.dwMinorVersion!=1||system.wProcessorArchitecture!=PROCESSOR_ARCHITECTURE_INTEL){event("blocked",L"Installer helper supports Windows XP x86 only",10);return 10;}
 if(AllocateAndInitializeSid(&auth,2,SECURITY_BUILTIN_DOMAIN_RID,DOMAIN_ALIAS_RID_ADMINS,0,0,0,0,0,0,&sid)){CheckTokenMembership(NULL,sid,&admin);FreeSid(sid);}if(!admin){event("blocked",L"Administrator account required for official capture driver installation",11);return 11;}
 if(!all_absent()){event("blocked",L"Existing or partial WinPcap installation; no automatic replacement",12);return 12;}
 locked=verify_file(argv[2]);if(locked==INVALID_HANDLE_VALUE){event("blocked",L"Official installer size/SHA256 mismatch or cannot lock/read file",13);return 13;}
 lstrcpyW(staging,argv[3]);lstrcatW(staging,L"\\official-installer");if(!CreateDirectoryW(staging,NULL)){CloseHandle(locked);event("blocked",L"Fresh installer staging directory required",14);return 14;}
 lstrcpyW(exe,staging);lstrcatW(exe,L"\\WinPcap_4_1_3.exe");if(!CopyFileW(argv[2],exe,TRUE)){CloseHandle(locked);return 15;}CloseHandle(locked);locked=verify_file(exe);if(locked==INVALID_HANDLE_VALUE)return 16;
 GetSystemDirectoryW(sys,MAX_PATH);SetDllDirectoryW(L"");ZeroMemory(&si,sizeof(si));si.cb=sizeof(si);ZeroMemory(&pi,sizeof(pi));wsprintfW(cmd,L"\"%s\"",exe);
 event("start",L"SHA256 and size verified. Running unchanged official installer; no silent/integrity-bypass switches",0);
 if(!CreateProcessW(exe,cmd,NULL,NULL,FALSE,0,NULL,sys,&si,&pi)){CloseHandle(locked);event("failed",L"CreateProcess failed",GetLastError());return 17;}installer_pid=pi.dwProcessId;start=last_good=GetTickCount();prior[0]=0;
 while(GetTickCount()-start<120000){DWORD_PTR result=0;DWORD now=GetTickCount();if(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0){GetExitCodeProcess(pi.hProcess,&exitcode);rc=stage==4&&exitcode==0&&has_installed_files()?0:32;break;}
  if(!inspect()){if(now-last_good>7000){event("blocked",L"No unique expected installer dialog; no additional clicks",33);rc=33;break;}Sleep(200);continue;}
  if(lstrcmpW(prior,page)){event("dialog",page,stage);lstrcpyW(prior,page);last_good=now;}
  if(inspect_only){event("inspect_only",L"Installer initial page recorded; no controls invoked. Installer remains open",0);rc=0;break;}
  if(stage==0&&contains(page,L"Welcome to the")&&contains(page,L"WinPcap 4.1.3")&&contains(page,L"Setup Wizard")){if(!click_button(L"&Next >"))break;stage=1;last_good=now;}
  else if(stage==1&&contains(page,L"License Agreement")&&contains(page,L"Redistribution and use in source and binary forms")){if(!click_button(L"I &Agree"))break;stage=2;last_good=now;}
  else if(stage==2&&contains(page,L"Installation options")&&option_count==1){
   LRESULT check=SendMessageW(option,BM_GETCHECK,0,0);if(check==BST_CHECKED){event("option",L"Disable automatic NPF start at boot; use on-demand capture driver",0);if(!SendMessageTimeoutW(option,BM_CLICK,0,0,SMTO_ABORTIFHUNG,2000,&result)||SendMessageW(option,BM_GETCHECK,0,0)!=BST_UNCHECKED)break;}else if(check!=BST_UNCHECKED)break;
   if(!click_button(L"&Install"))break;stage=3;last_good=now;
  }
  else if(stage==3&&contains(page,L"has been installed on your computer.")&&contains(page,L"Click Finish to close this wizard.")){if(contains(page,L"Reboot now")||contains(page,L"reboot the system")){event("blocked",L"Reboot requirement: no automatic reboot",34);rc=34;break;}if(!click_button(L"&Finish"))break;stage=4;last_good=now;}
  else if(now-last_good>25000){event("blocked",L"Unexpected or unchanging installer page; no further clicks",35);rc=35;break;}
  Sleep(250);
 }
 CloseHandle(pi.hThread);CloseHandle(pi.hProcess);CloseHandle(locked);event(rc?"incomplete":"complete",rc?L"Installer did not meet all guarded completion checks; inspect log and screen. No force termination or reboot.":L"Official installer completed and DLLs/npf exist. Caller must re-probe capture API/adapters.",rc);return rc;
}
void WINAPI provision_entry(void){int argc=0,rc;WCHAR**argv=CommandLineToArgvW(GetCommandLineW(),&argc);if(!argv)ExitProcess(2);rc=run(argc,argv);if(logfile)fclose(logfile);LocalFree(argv);ExitProcess(rc);}
unsigned long _tls_index=0;
