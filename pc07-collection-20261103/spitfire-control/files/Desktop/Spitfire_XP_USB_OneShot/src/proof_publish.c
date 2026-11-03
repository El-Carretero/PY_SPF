/* XP atomic publication of our passive-capture proof. No CRT or network APIs. */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

static WCHAR source_path[MAX_PATH],target_path[MAX_PATH];
static WCHAR source_parent[MAX_PATH],target_parent[MAX_PATH];

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
void WINAPI publish_entry(void) {
 int argc=0,rc=2;WCHAR **argv=CommandLineToArgvW(GetCommandLineW(),&argc);
 if(argv){rc=publish(argc,argv);LocalFree(argv);}ExitProcess((UINT)rc);
}
unsigned long _tls_index=0;
