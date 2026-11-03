/* XP atomic proof publication and a shared, bounded status snapshot reader.
 * No CRT, network, original-process access or input APIs. */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

static WCHAR source_path[MAX_PATH],target_path[MAX_PATH];
static WCHAR source_parent[MAX_PATH],target_parent[MAX_PATH];
static WCHAR snapshot_temp[MAX_PATH];
static BYTE snapshot_bytes[524288];

static int absolute_drive_path(const WCHAR *p) {
 return p&&((p[0]>=L'A'&&p[0]<=L'Z')||(p[0]>=L'a'&&p[0]<=L'z'))&&p[1]==L':'&&p[2]==L'\\';
}
static int publish(int argc,WCHAR **argv) {
 WCHAR *source_leaf=NULL,*target_leaf=NULL;DWORD n,attributes,error=0;int i;
 if(argc!=3||!absolute_drive_path(argv[1])||!absolute_drive_path(argv[2]))return 2;
 n=GetFullPathNameW(argv[1],MAX_PATH,source_path,&source_leaf);
 if(!n||n>=MAX_PATH||!source_leaf||lstrcmpiW(source_leaf,L"proof.tmp"))return 2;
 n=GetFullPathNameW(argv[2],MAX_PATH,target_path,&target_leaf);
 if(!n||n>=MAX_PATH||!target_leaf||lstrcmpiW(target_leaf,L"proof.txt"))return 2;
 lstrcpynW(source_parent,source_path,MAX_PATH);lstrcpynW(target_parent,target_path,MAX_PATH);
 source_parent[source_leaf-source_path]=0;target_parent[target_leaf-target_path]=0;
 if(lstrcmpiW(source_parent,target_parent))return 2;
 attributes=GetFileAttributesW(source_path);
 if(attributes==INVALID_FILE_ATTRIBUTES||(attributes&FILE_ATTRIBUTE_DIRECTORY))return 2;
 /* Failed replacement leaves the old proof untouched. Never delete first. */
 for(i=0;i<3;i++){
  if(MoveFileExW(source_path,target_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 0;
  error=GetLastError();
  /* XP may report a reader's missing FILE_SHARE_DELETE as access denied.
   * Retry it briefly, but do not classify persistent denial as a sharing error. */
  if(error!=ERROR_SHARING_VIOLATION&&error!=ERROR_LOCK_VIOLATION&&error!=ERROR_ACCESS_DENIED)return 2;
  if(i<2)Sleep(20);
 }
 return error==ERROR_ACCESS_DENIED?2:1;
}
static int snapshot_transient(DWORD error) {
 return error==ERROR_SHARING_VIOLATION||error==ERROR_LOCK_VIOLATION||
        error==ERROR_ACCESS_DENIED||error==ERROR_FILE_NOT_FOUND;
}
static int snapshot_paths(int argc,WCHAR **argv) {
 WCHAR *source_leaf=NULL,*target_leaf=NULL;DWORD n;int i,j;
 if(argc!=4||lstrcmpiW(argv[1],L"--snapshot")||
    !absolute_drive_path(argv[2])||!absolute_drive_path(argv[3]))return 0;
 n=GetFullPathNameW(argv[2],MAX_PATH,source_path,&source_leaf);
 if(!n||n>=MAX_PATH||!source_leaf||lstrcmpiW(source_leaf,L"status.json"))return 0;
 n=GetFullPathNameW(argv[3],MAX_PATH,target_path,&target_leaf);
 if(!n||n>=MAX_PATH||!target_leaf||lstrcmpiW(target_leaf,L"capture-status.json"))return 0;
 lstrcpynW(source_parent,source_path,MAX_PATH);lstrcpynW(target_parent,target_path,MAX_PATH);
 source_parent[source_leaf-source_path]=0;target_parent[target_leaf-target_path]=0;
 /* The only readable source is this run's capture/status.json; publication
  * is private to the orchestrator and never replaces the capture producer's file. */
 i=target_leaf-target_path;if(i+27>=MAX_PATH)return 0;
 lstrcpynW(snapshot_temp,target_parent,MAX_PATH);
 for(j=0;L"capture\\"[j];j++)snapshot_temp[i+j]=L"capture\\"[j];snapshot_temp[i+j]=0;
 if(lstrcmpiW(source_parent,snapshot_temp))return 0;
 for(j=0;L"capture-status-writing.tmp"[j];j++)snapshot_temp[i+j]=L"capture-status-writing.tmp"[j];snapshot_temp[i+j]=0;
 return 1;
}
static int snapshot_regular(HANDLE h,BY_HANDLE_FILE_INFORMATION *info) {
 return GetFileType(h)==FILE_TYPE_DISK&&GetFileInformationByHandle(h,info)&&
        !(info->dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT));
}
static int snapshot(int argc,WCHAR **argv) {
 HANDLE h=INVALID_HANDLE_VALUE;BY_HANDLE_FILE_INFORMATION before,after;
 DWORD error=0,size=0,got=0,total=0,attributes;BYTE extra;int i,rc=2;
 if(!snapshot_paths(argc,argv))return 2;
 for(i=0;i<3;i++){
  h=CreateFileW(source_path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h!=INVALID_HANDLE_VALUE)break;
  error=GetLastError();if(!snapshot_transient(error))return 2;if(i<2)Sleep(20);
 }
 if(h==INVALID_HANDLE_VALUE)return error==ERROR_ACCESS_DENIED?2:1;
 if(!snapshot_regular(h,&before)||before.nFileSizeHigh||!before.nFileSizeLow||
    before.nFileSizeLow>sizeof(snapshot_bytes))goto read_done;
 size=before.nFileSizeLow;
 while(total<size){
  if(!ReadFile(h,snapshot_bytes+total,size-total,&got,NULL)||!got)goto read_done;
  total+=got;
 }
 if(!ReadFile(h,&extra,1,&got,NULL)||got||!snapshot_regular(h,&after)||
    before.nFileSizeLow!=after.nFileSizeLow||after.nFileSizeHigh||
    before.ftLastWriteTime.dwLowDateTime!=after.ftLastWriteTime.dwLowDateTime||
    before.ftLastWriteTime.dwHighDateTime!=after.ftLastWriteTime.dwHighDateTime)goto read_done;
 rc=0;
 read_done:if(!CloseHandle(h))rc=2;if(rc)return rc;
 /* A failed read leaves the prior private snapshot untouched. It must never be
  * interpreted as a successful fresh snapshot unless this process returns 0. */
 attributes=GetFileAttributesW(snapshot_temp);
 if(attributes!=INVALID_FILE_ATTRIBUTES&&(attributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))return 2;
 attributes=GetFileAttributesW(target_path);
 if(attributes!=INVALID_FILE_ATTRIBUTES&&(attributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))return 2;
 h=CreateFileW(snapshot_temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,
               FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE)return 2;
 rc=2;total=0;
 if(!snapshot_regular(h,&after))goto write_done;
 while(total<size){
  if(!WriteFile(h,snapshot_bytes+total,size-total,&got,NULL)||!got)goto write_done;
  total+=got;
 }
 if(!FlushFileBuffers(h))goto write_done;rc=0;
 write_done:if(!CloseHandle(h))rc=2;if(rc)return rc;
 for(i=0;i<3;i++){
  if(MoveFileExW(snapshot_temp,target_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 0;
  error=GetLastError();
  if(error!=ERROR_SHARING_VIOLATION&&error!=ERROR_LOCK_VIOLATION&&error!=ERROR_ACCESS_DENIED)return 2;
  if(i<2)Sleep(20);
 }
 return error==ERROR_ACCESS_DENIED?2:1;
}
void WINAPI publish_entry(void) {
 int argc=0,rc=2;WCHAR **argv=CommandLineToArgvW(GetCommandLineW(),&argc);
 if(argv){rc=argc==4?snapshot(argc,argv):publish(argc,argv);LocalFree(argv);}ExitProcess((UINT)rc);
}
unsigned long _tls_index=0;
