/* XP x86 passive WinPcap collector. No sockets, packet injection, service start,
   adapter changes, or vendor-program interaction are implemented in this file. */
#define WINVER 0x0501
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "capture_protocol.h"
__declspec(dllimport) int __cdecl _snprintf(char *,size_t,const char *,...);
__declspec(dllimport) int __cdecl _wcsicmp(const wchar_t *,const wchar_t *);
__declspec(dllimport) LPWSTR * WINAPI CommandLineToArgvW(LPCWSTR,int *);
#define MAX_ADAPTERS 32
#define MAX_IPS 32
#define ERRBUF 256
#define LINE_SIZE 300000
#define SNAPLEN 65535
#define DLL_API(name,type,args) static type (__cdecl *name) args
struct pcap;typedef struct pcap pcap_t;
typedef struct pcap_addr_s {struct pcap_addr_s *next;struct sockaddr *addr,*netmask,*broadaddr,*dstaddr;} pcap_addr_t;
typedef struct pcap_if_s {struct pcap_if_s *next;char *name,*description;pcap_addr_t *addresses;unsigned flags;} pcap_if_t;
typedef struct {struct timeval ts;unsigned caplen,len;} pcap_pkthdr;
typedef struct {unsigned bf_len;void *bf_insns;} bpf_program;
typedef struct {unsigned ps_recv,ps_drop,ps_ifdrop,ps_capt;} pcap_stat;
DLL_API(p_findalldevs,int,(pcap_if_t **,char *));
DLL_API(p_freealldevs,void,(pcap_if_t *));
DLL_API(p_open_live,pcap_t *,(const char *,int,int,int,char *));
DLL_API(p_close,void,(pcap_t *));
DLL_API(p_datalink,int,(pcap_t *));
DLL_API(p_compile,int,(pcap_t *,bpf_program *,const char *,int,unsigned));
DLL_API(p_setfilter,int,(pcap_t *,bpf_program *));
DLL_API(p_freecode,void,(bpf_program *));
DLL_API(p_next_ex,int,(pcap_t *,pcap_pkthdr **,const unsigned char **));
DLL_API(p_setnonblock,int,(pcap_t *,int,char *));
DLL_API(p_stats,int,(pcap_t *,pcap_stat *));
DLL_API(p_geterr,char *,(pcap_t *));
DLL_API(p_lib_version,const char *,(void));
typedef struct {
 unsigned id,flags,ip_count,eligible,opened,finished,stats_valid;
 uint32_t ips[MAX_IPS];
 char name[512],description[512],error[512],skip_reason[96];
 pcap_t *pcap;HANDLE file,thread;
 unsigned frames,udp_frames,command_frames,response_frames,truncated_frames;
 unsigned pcap_validation_done,pcap_validation_ok,pcap_validated_frames;
 pcap_stat stats;
} adapter;
typedef struct {char *data;size_t pos,capacity;int bad;} json;
static adapter adapters[MAX_ADAPTERS];
static unsigned adapter_count,active_adapters,adapter_errors,enumeration_overflow;
static cap_observation observations;
static CRITICAL_SECTION state_lock;
unsigned long _tls_index=0; /* Zig link contract; no TLS is used. */
static HANDLE capture_mutex;
static HANDLE stop_event,packet_log=INVALID_HANDLE_VALUE,adapter_log=INVALID_HANDLE_VALUE;
static WCHAR output_dir[MAX_PATH],global_stop[MAX_PATH],local_stop[MAX_PATH];
static WCHAR dll_path[MAX_PATH],packet_dll_path[MAX_PATH];
static HMODULE pcap_module,packet_module;
static char load_error[512],first_write_command[512],first_write_utc[40];
static unsigned first_write_sec,first_write_usec,io_errors,status_errors,sequence;
static int stopping,initialized;
static char packet_line[LINE_SIZE],status_line[524288],probe_line[300000];
static char lib_version[512];
typedef struct {unsigned tag,kind,count,first_sec,first_usec,last_sec,last_usec,min_interval_us,max_interval_us,out_of_order;} tag_stat;
static tag_stat tag_stats[256];
static unsigned tag_stat_count,tag_stat_overflow;
static DWORD run_started,run_seconds=120;
static unsigned status_generation;
static void ascii_copy(char *d,size_t cap,const char *s) {size_t n=0;if(!s)s="";while(n+1<cap&&s[n]){d[n]=s[n];n++;}d[n]=0;}
static int wide_copy(WCHAR *d,size_t cap,const WCHAR *s) {size_t i=0;while(s[i]){if(i+1>=cap)return 0;d[i]=s[i];i++;}d[i]=0;return 1;}
static int append_path(WCHAR *d,const WCHAR *base,const WCHAR *name) {size_t n=0,k=0;while(base[n])n++;if(n+1>=MAX_PATH)return 0;memcpy(d,base,n*sizeof(WCHAR));if(n&&d[n-1]!='\\'&&d[n-1]!='/')d[n++]='\\';while(name[k]){if(n+1>=MAX_PATH)return 0;d[n++]=name[k++];}d[n]=0;return 1;}
static void utc_now(char *b,size_t n) {SYSTEMTIME t;GetSystemTime(&t);_snprintf(b,n,"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds);b[n-1]=0;}
static void ip_text(uint32_t ip,char *b) {_snprintf(b,32,"%u.%u.%u.%u",ip>>24,(ip>>16)&255,(ip>>8)&255,ip&255);}
static void j_init(json *j,char *b,size_t n){j->data=b;j->pos=0;j->capacity=n;j->bad=0;b[0]=0;}
static void j_raw(json *j,const char *s){size_t n=strlen(s);if(j->pos+n>=j->capacity){j->bad=1;return;}memcpy(j->data+j->pos,s,n);j->pos+=n;j->data[j->pos]=0;}
static void j_uint(json *j,unsigned x){char b[32];_snprintf(b,sizeof(b),"%u",x);j_raw(j,b);}
static void j_bool(json *j,int x){j_raw(j,x?"true":"false");}
static void j_bytes(json *j,const unsigned char *s,size_t n){size_t i;char b[8];j_raw(j,"\"");for(i=0;i<n;i++){unsigned c=s[i];if(c=='"')j_raw(j,"\\\"");else if(c=='\\')j_raw(j,"\\\\");else if(c>=32&&c<127){b[0]=(char)c;b[1]=0;j_raw(j,b);}else{_snprintf(b,sizeof(b),"\\u%04x",c);j_raw(j,b);}}j_raw(j,"\"");}
static void j_str(json *j,const char *s){j_bytes(j,(const unsigned char *)(s?s:""),s?strlen(s):0);}
static void j_wide(json *j,const WCHAR *s){/* Paths represented as Unicode JSON escapes. */char b[8];j_raw(j,"\"");while(*s){unsigned c=*s++;if(c=='"')j_raw(j,"\\\"");else if(c=='\\')j_raw(j,"\\\\");else if(c>=32&&c<127){b[0]=(char)c;b[1]=0;j_raw(j,b);}else{_snprintf(b,sizeof(b),"\\u%04x",c);j_raw(j,b);}}j_raw(j,"\"");}
static void j_hex(json *j,const unsigned char *s,size_t n){static const char h[]="0123456789abcdef";size_t i;char b[3];j_raw(j,"\"");for(i=0;i<n;i++){b[0]=h[s[i]>>4];b[1]=h[s[i]&15];b[2]=0;j_raw(j,b);}j_raw(j,"\"");}
static int write_all(HANDLE h,const void *data,DWORD n){DWORD wrote=0;return h!=INVALID_HANDLE_VALUE&&WriteFile(h,data,n,&wrote,NULL)&&wrote==n;}
static int write_json(HANDLE h,json *j){return !j->bad&&write_all(h,j->data,(DWORD)j->pos);}
static void fail_io(void){InterlockedIncrement((LONG *)&io_errors);if(stop_event)SetEvent(stop_event);}
static int file_exists(const WCHAR *p){DWORD a=GetFileAttributesW(p);return a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY);}
static int module_path_ok(HMODULE h,const WCHAR *expected){WCHAR path[MAX_PATH];DWORD n=GetModuleFileNameW(h,path,MAX_PATH);return n>0&&n<MAX_PATH&&_wcsicmp(path,expected)==0;}
static int load_pcap(void) {
 WCHAR system[MAX_PATH];DWORD len=GetSystemDirectoryW(system,MAX_PATH);
 if(!len||len>=MAX_PATH||!append_path(dll_path,system,L"wpcap.dll")||!append_path(packet_dll_path,system,L"Packet.dll")){ascii_copy(load_error,sizeof(load_error),"System32 path unavailable");return 21;}
 if(!file_exists(dll_path)){ascii_copy(load_error,sizeof(load_error),"System32 wpcap.dll missing");return 20;}
 if(!file_exists(packet_dll_path)){ascii_copy(load_error,sizeof(load_error),"System32 Packet.dll missing (partial installation)");return 21;}
 /* Remove current directory; preload the system Packet dependency explicitly. */
 if(!SetDllDirectoryW(L"")){ascii_copy(load_error,sizeof(load_error),"SetDllDirectoryW failed");return 21;}
 packet_module=LoadLibraryExW(packet_dll_path,NULL,LOAD_WITH_ALTERED_SEARCH_PATH);
 if(!packet_module||!module_path_ok(packet_module,packet_dll_path)){ascii_copy(load_error,sizeof(load_error),"System32 Packet.dll load/path verification failed");return 21;}
 pcap_module=LoadLibraryExW(dll_path,NULL,LOAD_WITH_ALTERED_SEARCH_PATH);
 if(!pcap_module||!module_path_ok(pcap_module,dll_path)){ascii_copy(load_error,sizeof(load_error),"System32 wpcap.dll load/path verification failed");return 21;}
#define RESOLVE(name) do { *(FARPROC *)&p_##name=GetProcAddress(pcap_module,"pcap_" #name);if(!p_##name){ascii_copy(load_error,sizeof(load_error),"Missing export pcap_" #name);return 21;} } while(0)
 RESOLVE(findalldevs);RESOLVE(freealldevs);RESOLVE(open_live);RESOLVE(close);RESOLVE(datalink);RESOLVE(compile);RESOLVE(setfilter);RESOLVE(freecode);RESOLVE(next_ex);RESOLVE(setnonblock);RESOLVE(stats);RESOLVE(geterr);RESOLVE(lib_version);
#undef RESOLVE
 ascii_copy(lib_version,sizeof(lib_version),p_lib_version());return 0;
}
static void npf_status(json *j){SC_HANDLE manager,service;SERVICE_STATUS st;DWORD error=0;unsigned state=0;int exists=0,readable=0;
 manager=OpenSCManagerW(NULL,NULL,SC_MANAGER_CONNECT);
 if(manager){service=OpenServiceW(manager,L"NPF",SERVICE_QUERY_STATUS);if(service){exists=1;if(QueryServiceStatus(service,&st)){readable=1;state=st.dwCurrentState;}else error=GetLastError();CloseServiceHandle(service);}else error=GetLastError();CloseServiceHandle(manager);}else error=GetLastError();
 j_raw(j,"{\"exists\":");j_bool(j,exists);j_raw(j,",\"readable\":");j_bool(j,readable);j_raw(j,",\"state\":");j_uint(j,state);j_raw(j,",\"windows_error\":");j_uint(j,error);j_raw(j,"}");
}
static int enumerate_adapters(void){pcap_if_t *list=NULL,*d;char err[ERRBUF]={0};if(p_findalldevs(&list,err)<0){ascii_copy(load_error,sizeof(load_error),err);return 21;}
 for(d=list;d;d=d->next){adapter *a;pcap_addr_t *addr;
  if(adapter_count==MAX_ADAPTERS){enumeration_overflow=1;continue;}
  a=adapters+adapter_count;memset(a,0,sizeof(*a));a->id=adapter_count+1;adapter_count++;a->file=INVALID_HANDLE_VALUE;a->flags=d->flags;
  ascii_copy(a->name,sizeof(a->name),d->name);ascii_copy(a->description,sizeof(a->description),d->description);
  for(addr=d->addresses;addr;addr=addr->next)if(addr->addr&&addr->addr->sa_family==AF_INET){const unsigned char *b=(const unsigned char *)&((struct sockaddr_in *)addr->addr)->sin_addr;uint32_t ip=((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|b[3];if(ip&&((ip>>24)!=127)){if(a->ip_count<MAX_IPS)a->ips[a->ip_count++]=ip;else enumeration_overflow=1;}}
  if(a->flags&1)ascii_copy(a->skip_reason,sizeof(a->skip_reason),"loopback");
  else if(!a->ip_count)ascii_copy(a->skip_reason,sizeof(a->skip_reason),"no non-loopback IPv4 address");
  else if(!d->name||strlen(d->name)>=sizeof(a->name))ascii_copy(a->error,sizeof(a->error),"adapter name too long");
  else a->eligible=1;
 }
 p_freealldevs(list);return 0;
}
static void adapter_json(json *j,const adapter *a){unsigned k;char ip[32];
 j_raw(j,"{\"interface_id\":");j_uint(j,a->id);j_raw(j,",\"name\":");j_str(j,a->name);j_raw(j,",\"description\":");j_str(j,a->description);j_raw(j,",\"ipv4\":[");for(k=0;k<a->ip_count;k++){if(k)j_raw(j,",");ip_text(a->ips[k],ip);j_str(j,ip);}j_raw(j,"],\"eligible\":");j_bool(j,a->eligible);j_raw(j,",\"opened\":");j_bool(j,a->opened);j_raw(j,",\"finished\":");j_bool(j,a->finished);j_raw(j,",\"skip_reason\":");j_str(j,a->skip_reason);j_raw(j,",\"error\":");j_str(j,a->error);j_raw(j,",\"frames\":");j_uint(j,a->frames);j_raw(j,",\"udp_frames\":");j_uint(j,a->udp_frames);j_raw(j,",\"command_packets\":");j_uint(j,a->command_frames);j_raw(j,",\"response_packets\":");j_uint(j,a->response_frames);j_raw(j,",\"truncated_frames\":");j_uint(j,a->truncated_frames);j_raw(j,",\"pcap_validation_done\":");j_bool(j,a->pcap_validation_done);j_raw(j,",\"pcap_validation_ok\":");j_bool(j,a->pcap_validation_ok);j_raw(j,",\"pcap_validated_frames\":");j_uint(j,a->pcap_validated_frames);j_raw(j,",\"stats_supported\":");j_bool(j,a->stats_valid);j_raw(j,",\"ps_recv\":");j_uint(j,a->stats.ps_recv);j_raw(j,",\"ps_drop\":");j_uint(j,a->stats.ps_drop);j_raw(j,",\"ps_ifdrop\":");j_uint(j,a->stats.ps_ifdrop);j_raw(j,"}");
}
static int probe(const WCHAR *output){json j;int result=load_pcap();unsigned k;HANDLE h=GetStdHandle(STD_OUTPUT_HANDLE);if(!result)result=enumerate_adapters();j_init(&j,probe_line,sizeof(probe_line));
 j_raw(&j,"{\"schema\":1,\"mode\":\"read_only_probe\",\"exit_code\":");j_uint(&j,result);j_raw(&j,",\"winpcap_version\":");j_str(&j,lib_version);j_raw(&j,",\"wpcap_path\":");j_wide(&j,dll_path);j_raw(&j,",\"packet_path\":");j_wide(&j,packet_dll_path);j_raw(&j,",\"error\":");j_str(&j,load_error);j_raw(&j,",\"npf_service\":");npf_status(&j);j_raw(&j,",\"enumeration_overflow\":");j_bool(&j,enumeration_overflow);j_raw(&j,",\"adapters\":[");for(k=0;k<adapter_count;k++){if(k)j_raw(&j,",");adapter_json(&j,adapters+k);}j_raw(&j,"]}\r\n");
 if(output){h=CreateFileW(output,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);if(h==INVALID_HANDLE_VALUE)return 23;}
 if(!write_json(h,&j))result=23;
 if(output)CloseHandle(h);return result;
}
static void adapter_error(adapter *a,const char *message){EnterCriticalSection(&state_lock);if(!a->error[0])adapter_errors++;ascii_copy(a->error,sizeof(a->error),message);LeaveCriticalSection(&state_lock);}
static int is_local(adapter *a,uint32_t ip){unsigned k;for(k=0;k<a->ip_count;k++)if(a->ips[k]==ip)return 1;return 0;}
static int pcap_header(HANDLE h){static const unsigned char hdr[24]={0xd4,0xc3,0xb2,0xa1,2,0,4,0,0,0,0,0,0,0,0,0,0xff,0xff,0,0,1,0,0,0};return write_all(h,hdr,24);}
static int save_frame(adapter *a,const pcap_pkthdr *h,const unsigned char *bytes){uint32_t fields[4];if(h->caplen>SNAPLEN||h->caplen>h->len||h->ts.tv_usec<0||h->ts.tv_usec>=1000000)return 0;fields[0]=(uint32_t)h->ts.tv_sec;fields[1]=(uint32_t)h->ts.tv_usec;fields[2]=h->caplen;fields[3]=h->len;return write_all(a->file,fields,16)&&write_all(a->file,bytes,h->caplen);}
static void note_tag(const cap_packet *p,const pcap_pkthdr *h){unsigned k;tag_stat *t;unsigned sec=(unsigned)h->ts.tv_sec,usec=(unsigned)h->ts.tv_usec;
 if(!p->kind||!p->tag)return;
 for(k=0;k<tag_stat_count;k++)if(tag_stats[k].tag==p->tag&&tag_stats[k].kind==p->kind)break;
 if(k==tag_stat_count){if(k==256){tag_stat_overflow=1;return;}t=tag_stats+k;t->tag=p->tag;t->kind=p->kind;t->first_sec=sec;t->first_usec=usec;t->min_interval_us=0xffffffffU;tag_stat_count++;}
 t=tag_stats+k;
 if(t->count){if(sec<t->last_sec||(sec==t->last_sec&&usec<t->last_usec))t->out_of_order++;else{unsigned interval=(sec-t->last_sec)*1000000U+usec-t->last_usec;if(interval<t->min_interval_us)t->min_interval_us=interval;if(interval>t->max_interval_us)t->max_interval_us=interval;}}
 t->count++;t->last_sec=sec;t->last_usec=usec;
}
static void log_packet(adapter *a,const pcap_pkthdr *h,const unsigned char *bytes){cap_packet p;json j;char utc[40],src[32],dst[32];int decoded=cap_decode_ethernet(bytes,h->caplen,&p);DWORD now=GetTickCount();utc_now(utc,sizeof(utc));
 EnterCriticalSection(&state_lock);a->frames++;if(h->caplen<h->len)a->truncated_frames++;
 if(decoded){unsigned old_writes=observations.any_write_commands;a->udp_frames++;if(p.kind==CAP_COMMAND)a->command_frames++;if(p.kind==CAP_RESPONSE)a->response_frames++;
 cap_observe(&observations,&p,a->id,is_local(a,p.src_ip),is_local(a,p.dst_ip),now);note_tag(&p,h);
 if(!old_writes&&observations.any_write_commands){size_t n=p.payload_len;if(n>=sizeof(first_write_command))n=sizeof(first_write_command)-1;memcpy(first_write_command,p.payload,n);first_write_command[n]=0;ascii_copy(first_write_utc,sizeof(first_write_utc),utc);first_write_sec=(unsigned)h->ts.tv_sec;first_write_usec=(unsigned)h->ts.tv_usec;}}
 j_init(&j,packet_line,sizeof(packet_line));j_raw(&j,"{\"seq\":");j_uint(&j,++sequence);j_raw(&j,",\"observed_utc\":");j_str(&j,utc);j_raw(&j,",\"tick_ms\":");j_uint(&j,now);j_raw(&j,",\"pcap_sec\":");j_uint(&j,(unsigned)h->ts.tv_sec);j_raw(&j,",\"pcap_usec\":");j_uint(&j,(unsigned)h->ts.tv_usec);j_raw(&j,",\"interface_id\":");j_uint(&j,a->id);j_raw(&j,",\"frame_index\":");j_uint(&j,a->frames);j_raw(&j,",\"captured_length\":");j_uint(&j,h->caplen);j_raw(&j,",\"original_length\":");j_uint(&j,h->len);j_raw(&j,",\"decoded_udp1024\":");j_bool(&j,decoded);
 if(decoded){ip_text(p.src_ip,src);ip_text(p.dst_ip,dst);j_raw(&j,",\"src_ip\":");j_str(&j,src);j_raw(&j,",\"src_port\":");j_uint(&j,p.src_port);j_raw(&j,",\"dst_ip\":");j_str(&j,dst);j_raw(&j,",\"dst_port\":");j_uint(&j,p.dst_port);j_raw(&j,",\"kind\":");j_str(&j,p.kind==CAP_COMMAND?"command":p.kind==CAP_RESPONSE?"response":"other");j_raw(&j,",\"first_tag\":");j_uint(&j,p.tag);j_raw(&j,",\"write_commands\":");j_uint(&j,p.write_commands);j_raw(&j,",\"malformed_command\":");j_bool(&j,p.malformed_command);j_raw(&j,",\"payload_hex\":");j_hex(&j,p.payload,p.payload_len);}
 j_raw(&j,"}\r\n");if(!write_json(packet_log,&j))fail_io();LeaveCriticalSection(&state_lock);
}
static DWORD WINAPI capture_worker(LPVOID argument){adapter *a=(adapter *)argument;DWORD last_stats=0;
 while(WaitForSingleObject(stop_event,0)==WAIT_TIMEOUT){pcap_pkthdr *h;const unsigned char *data;int r=p_next_ex(a->pcap,&h,&data);
  if(r==1){if(!save_frame(a,h,data)){adapter_error(a,"PCAP write failure or invalid capture header");fail_io();break;}log_packet(a,h,data);}
  else if(r==0)Sleep(15);
  else {adapter_error(a,r==-2?"capture unexpectedly ended":p_geterr(a->pcap));break;}
  if((DWORD)(GetTickCount()-last_stats)>=1000){pcap_stat s={0};int ok=p_stats(a->pcap,&s)==0;EnterCriticalSection(&state_lock);a->stats_valid=ok;if(ok)a->stats=s;LeaveCriticalSection(&state_lock);last_stats=GetTickCount();}
 }
 {pcap_stat s={0};int ok=p_stats(a->pcap,&s)==0;EnterCriticalSection(&state_lock);a->stats_valid=ok;if(ok)a->stats=s;LeaveCriticalSection(&state_lock);}
 p_close(a->pcap);a->pcap=NULL;if(!FlushFileBuffers(a->file))fail_io();CloseHandle(a->file);a->file=INVALID_HANDLE_VALUE;EnterCriticalSection(&state_lock);a->finished=1;LeaveCriticalSection(&state_lock);return 0;
}
static int open_adapters(void){unsigned k;for(k=0;k<adapter_count;k++){adapter *a=adapters+k;char err[ERRBUF]={0};bpf_program filter;WCHAR filename[40],path[MAX_PATH];
 if(!a->eligible){if(a->error[0])adapter_errors++;continue;}
 a->pcap=p_open_live(a->name,SNAPLEN,0,250,err);
 if(!a->pcap){adapter_error(a,err);continue;}
 if(p_datalink(a->pcap)!=1){ascii_copy(a->skip_reason,sizeof(a->skip_reason),"not Ethernet DLT_EN10MB");p_close(a->pcap);a->pcap=NULL;a->eligible=0;continue;}
 if(p_compile(a->pcap,&filter,"udp port 1024",1,0xffffffffU)<0){adapter_error(a,p_geterr(a->pcap));p_close(a->pcap);a->pcap=NULL;continue;}
 if(p_setfilter(a->pcap,&filter)<0){adapter_error(a,p_geterr(a->pcap));p_freecode(&filter);p_close(a->pcap);a->pcap=NULL;continue;}p_freecode(&filter);
 if(p_setnonblock(a->pcap,1,err)<0){adapter_error(a,err);p_close(a->pcap);a->pcap=NULL;continue;}
 /* Filename uses a stable index; every PCAP is an independent complete file. */
 {char name[40];_snprintf(name,sizeof(name),"adapter-%02u.pcap",a->id);MultiByteToWideChar(CP_ACP,0,name,-1,filename,40);}
 if(!append_path(path,output_dir,filename)){adapter_error(a,"output path too long");p_close(a->pcap);a->pcap=NULL;continue;}
 a->file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
 if(a->file==INVALID_HANDLE_VALUE||!pcap_header(a->file)){adapter_error(a,"cannot create PCAP");if(a->file!=INVALID_HANDLE_VALUE)CloseHandle(a->file);p_close(a->pcap);a->pcap=NULL;fail_io();continue;}
 a->opened=1;active_adapters++;
 }
 for(k=0;k<adapter_count;k++){adapter *a=adapters+k;if(a->opened){a->thread=CreateThread(NULL,0,capture_worker,a,0,NULL);if(!a->thread){adapter_error(a,"CreateThread failed");p_close(a->pcap);a->pcap=NULL;CloseHandle(a->file);a->file=INVALID_HANDLE_VALUE;a->finished=1;active_adapters--;}}}
 return active_adapters>0;
}
static int atomic_output(const WCHAR *name,const char *data,DWORD length){WCHAR path[MAX_PATH],temp[MAX_PATH];HANDLE h;unsigned tries;
 if(!append_path(path,output_dir,name)||!append_path(temp,output_dir,L"status-writing.tmp"))return 0;
 h=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);if(h==INVALID_HANDLE_VALUE)return 0;
 if(!write_all(h,data,length)||!FlushFileBuffers(h)){CloseHandle(h);return 0;}CloseHandle(h);
 for(tries=0;tries<4;tries++){if(MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 1;Sleep(10);}return 0;
}
static const char *blocked_reason(DWORD now,unsigned drops){unsigned k;if(stopping)return "capture_stopped";if(!initialized)return "initializing";if(io_errors)return "capture_io_error";if(status_errors)return "status_publication_error_latched";if(adapter_errors)return "adapter_error_unobserved_interface";if(enumeration_overflow)return "too_many_interfaces_or_addresses";if(!active_adapters)return "no_eligible_capture_adapter";for(k=0;k<adapter_count;k++)if(adapters[k].opened){if(adapters[k].truncated_frames)return "truncated_capture_frame";if(!adapters[k].stats_valid)return "capture_statistics_unavailable";}if(observations.any_write_commands)return "write_command_observed_ui_stop_latched";if(observations.malformed_commands)return "unrecognized_command_format";if(drops)return "capture_drop_observed";if(observations.pair_overflow||observations.pair_count>1)return "ambiguous_endpoint_pairs_or_interfaces";if(!observations.pair_count||!observations.command_packets)return "no_original_command_traffic";if(!observations.response_packets)return "no_reverse_reply_traffic";if(!cap_pair_ready(&observations,now))return "waiting_for_three_recent_packets_each_direction";return "";}
static void publish_status(int final){json j;char utc[40],ip[32];unsigned k,drops=0,truncated=0,stats_unavailable=0,all_pcap_valid=active_adapters>0;DWORD now=GetTickCount();const char *reason;utc_now(utc,sizeof(utc));EnterCriticalSection(&state_lock);
 for(k=0;k<adapter_count;k++){drops+=adapters[k].stats.ps_drop+adapters[k].stats.ps_ifdrop;truncated+=adapters[k].truncated_frames;if(adapters[k].opened&&!adapters[k].stats_valid)stats_unavailable++;if(adapters[k].opened&&!adapters[k].pcap_validation_ok)all_pcap_valid=0;}
 reason=blocked_reason(now,drops);j_init(&j,status_line,sizeof(status_line));j_raw(&j,"{\"schema\":1,\"generation\":");j_uint(&j,++status_generation);j_raw(&j,",\"updated_utc\":");j_str(&j,utc);j_raw(&j,",\"tick_ms\":");j_uint(&j,now);j_raw(&j,",\"updated_tick\":");j_uint(&j,now);j_raw(&j,",\"elapsed_ms\":");j_uint(&j,now-run_started);j_raw(&j,",\"stage\":");j_str(&j,stopping?"stopped":initialized?"capturing":"initializing");j_raw(&j,",\"capture_ready\":");j_bool(&j,initialized&&!stopping&&active_adapters&&!adapter_errors&&!io_errors&&!enumeration_overflow);j_raw(&j,",\"ui_ready\":");j_bool(&j,!reason[0]);j_raw(&j,",\"blocked_reason\":");j_str(&j,reason);j_raw(&j,",\"output_directory\":");j_wide(&j,output_dir);j_raw(&j,",\"winpcap_version\":");j_str(&j,lib_version);j_raw(&j,",\"filter\":\"udp port 1024\",\"promiscuous\":false,\"snaplen\":65535,\"pcap_linktype\":1,\"transmission_supported\":false,\"active_adapters\":");j_uint(&j,active_adapters);j_raw(&j,",\"candidate_pairs\":");j_uint(&j,observations.pair_count);j_raw(&j,",\"observed_pairs\":");j_uint(&j,observations.pair_count);j_raw(&j,",\"command_packets\":");j_uint(&j,observations.command_packets);j_raw(&j,",\"response_packets\":");j_uint(&j,observations.response_packets);j_raw(&j,",\"any_write_commands\":");j_uint(&j,observations.any_write_commands);j_raw(&j,",\"first_write_tag\":");j_uint(&j,observations.first_write_tag);j_raw(&j,",\"first_write_command\":");j_str(&j,first_write_command);j_raw(&j,",\"first_write_utc\":");j_str(&j,first_write_utc);j_raw(&j,",\"first_write_pcap_sec\":");j_uint(&j,first_write_sec);j_raw(&j,",\"first_write_pcap_usec\":");j_uint(&j,first_write_usec);j_raw(&j,",\"malformed_commands\":");j_uint(&j,observations.malformed_commands);j_raw(&j,",\"adapter_errors\":");j_uint(&j,adapter_errors);j_raw(&j,",\"io_errors\":");j_uint(&j,io_errors);j_raw(&j,",\"status_write_errors\":");j_uint(&j,status_errors);j_raw(&j,",\"capture_drops\":");j_uint(&j,drops);j_raw(&j,",\"truncated_frames\":");j_uint(&j,truncated);j_raw(&j,",\"capture_stats_unavailable\":");j_uint(&j,stats_unavailable);j_raw(&j,",\"enumeration_overflow\":");j_bool(&j,enumeration_overflow);j_raw(&j,",\"pcap_validation_ok\":");j_bool(&j,all_pcap_valid);j_raw(&j,",\"initialization_error\":");j_str(&j,load_error);
 if(observations.pair_count==1){cap_pair *p=observations.pairs;ip_text(p->client_ip,ip);j_raw(&j,",\"command_src_ip\":");j_str(&j,ip);j_raw(&j,",\"command_src_port\":");j_uint(&j,p->client_port);ip_text(p->controller_ip,ip);j_raw(&j,",\"controller_ip\":");j_str(&j,ip);j_raw(&j,",\"controller_port\":");j_uint(&j,p->controller_port);j_raw(&j,",\"interface_id\":");j_uint(&j,p->interface_id);}
 j_raw(&j,",\"pairs\":[");for(k=0;k<observations.pair_count;k++){cap_pair *p=observations.pairs+k;if(k)j_raw(&j,",");j_raw(&j,"{\"interface_id\":");j_uint(&j,p->interface_id);ip_text(p->client_ip,ip);j_raw(&j,",\"command_src_ip\":");j_str(&j,ip);j_raw(&j,",\"command_src_port\":");j_uint(&j,p->client_port);ip_text(p->controller_ip,ip);j_raw(&j,",\"controller_ip\":");j_str(&j,ip);j_raw(&j,",\"controller_port\":");j_uint(&j,p->controller_port);j_raw(&j,",\"commands\":");j_uint(&j,p->commands);j_raw(&j,",\"responses\":");j_uint(&j,p->responses);j_raw(&j,",\"last_command_age_ms\":");j_uint(&j,now-p->last_command_ms);j_raw(&j,",\"last_response_age_ms\":");j_uint(&j,now-p->last_response_ms);j_raw(&j,"}");}
 j_raw(&j,"],\"tag_statistics_first_message_only\":true,\"tag_stat_overflow\":");j_bool(&j,tag_stat_overflow);j_raw(&j,",\"tag_statistics\":[");
 for(k=0;k<tag_stat_count;k++){tag_stat *t=tag_stats+k;if(k)j_raw(&j,",");j_raw(&j,"{\"tag\":");j_uint(&j,t->tag);j_raw(&j,",\"kind\":");j_str(&j,t->kind==CAP_COMMAND?"command":"response");j_raw(&j,",\"count\":");j_uint(&j,t->count);j_raw(&j,",\"first_sec\":");j_uint(&j,t->first_sec);j_raw(&j,",\"first_usec\":");j_uint(&j,t->first_usec);j_raw(&j,",\"last_sec\":");j_uint(&j,t->last_sec);j_raw(&j,",\"last_usec\":");j_uint(&j,t->last_usec);j_raw(&j,",\"min_interval_us\":");j_uint(&j,t->min_interval_us==0xffffffffU?0:t->min_interval_us);j_raw(&j,",\"max_interval_us\":");j_uint(&j,t->max_interval_us);j_raw(&j,",\"periods_valid\":");j_bool(&j,!t->out_of_order);j_raw(&j,",\"mean_interval_us\":");j_uint(&j,t->count>1&&!t->out_of_order?((t->last_sec-t->first_sec)*1000000U+t->last_usec-t->first_usec)/(t->count-1):0);j_raw(&j,",\"out_of_order_timestamps\":");j_uint(&j,t->out_of_order);j_raw(&j,"}");}
 j_raw(&j,"],\"adapters\":[");for(k=0;k<adapter_count;k++){if(k)j_raw(&j,",");adapter_json(&j,adapters+k);}j_raw(&j,"]}\r\n");LeaveCriticalSection(&state_lock);
 if(j.bad||!atomic_output(final?L"summary.json":L"status.json",j.data,(DWORD)j.pos))status_errors++;
}
/* Independently re-read each finished classic PCAP through Win32 file IO.
   Check actual complete records, full payload availability, and capture counts. */
static unsigned char validation_bytes[4096];
static int validate_pcap_file(adapter *a){WCHAR name[40],path[MAX_PATH];char ansi[40];HANDLE h;unsigned char header[24];DWORD got;unsigned count=0;int ok=1;
 _snprintf(ansi,sizeof(ansi),"adapter-%02u.pcap",a->id);MultiByteToWideChar(CP_ACP,0,ansi,-1,name,40);
 a->pcap_validation_done=1;if(!append_path(path,output_dir,name))return 0;
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);if(h==INVALID_HANDLE_VALUE)return 0;
 if(!ReadFile(h,header,24,&got,NULL)||got!=24||header[0]!=0xd4||header[1]!=0xc3||header[2]!=0xb2||header[3]!=0xa1||header[4]!=2||header[5]!=0||header[6]!=4||header[7]!=0||header[16]!=0xff||header[17]!=0xff||header[18]!=0||header[19]!=0||header[20]!=1||header[21]!=0||header[22]!=0||header[23]!=0)ok=0;
 while(ok){uint32_t fields[4];unsigned remain;if(!ReadFile(h,fields,16,&got,NULL)){ok=0;break;}if(!got)break;if(got!=16||fields[1]>=1000000||fields[2]>SNAPLEN||fields[2]>fields[3]){ok=0;break;}remain=fields[2];
  while(remain){DWORD take=remain>sizeof(validation_bytes)?sizeof(validation_bytes):remain;if(!ReadFile(h,validation_bytes,take,&got,NULL)||got!=take){ok=0;break;}remain-=got;}if(ok)count++;
 }
 CloseHandle(h);a->pcap_validated_frames=count;a->pcap_validation_ok=ok&&count==a->frames;return a->pcap_validation_ok;
}
static BOOL WINAPI console_ctrl(DWORD event){if(event==CTRL_C_EVENT||event==CTRL_BREAK_EVENT||event==CTRL_CLOSE_EVENT){if(stop_event)SetEvent(stop_event);return TRUE;}return FALSE;}
static unsigned parse_seconds(const WCHAR *s){unsigned v=0;while(*s){if(*s<'0'||*s>'9')return 0;v=v*10+(*s++-'0');if(v>900)return 0;}return v>=5?v:0;}
static int capture_run(int argc,WCHAR **argv){unsigned k;WCHAR path[MAX_PATH];int result;json j;
 if(argc<2||argc>4)return 2;
 capture_mutex=CreateMutexW(NULL,FALSE,L"Global\\SpitfirePassiveCaptureV1");if(!capture_mutex||GetLastError()==ERROR_ALREADY_EXISTS)return 23;if(argc>=3){run_seconds=parse_seconds(argv[2]);if(!run_seconds)return 2;}
 if(!wide_copy(output_dir,MAX_PATH,argv[1])||(argc==4&&!wide_copy(global_stop,MAX_PATH,argv[3]))||!append_path(local_stop,output_dir,L"STOP"))return 2;
 /* Caller must supply a fresh directory, preventing accidental append/replay. */
 if(!CreateDirectoryW(output_dir,NULL))return 23;
 InitializeCriticalSection(&state_lock);run_started=GetTickCount();stop_event=CreateEventW(NULL,TRUE,FALSE,NULL);if(!stop_event)return 23;SetConsoleCtrlHandler(console_ctrl,TRUE);
 if(!append_path(path,output_dir,L"packets.jsonl"))return 23;packet_log=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
 if(!append_path(path,output_dir,L"adapters.jsonl"))return 23;adapter_log=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
 if(packet_log==INVALID_HANDLE_VALUE||adapter_log==INVALID_HANDLE_VALUE){fail_io();result=23;goto finish;}
 result=load_pcap();if(result){adapter_errors++;goto finish;}result=enumerate_adapters();if(result){adapter_errors++;goto finish;}
 open_adapters();initialized=1;
 for(k=0;k<adapter_count;k++){j_init(&j,status_line,sizeof(status_line));adapter_json(&j,adapters+k);j_raw(&j,"\r\n");if(!write_json(adapter_log,&j))fail_io();}
 publish_status(0);
 while(active_adapters&&WaitForSingleObject(stop_event,250)==WAIT_TIMEOUT){if(file_exists(local_stop)||(global_stop[0]&&file_exists(global_stop))||(DWORD)(GetTickCount()-run_started)>=run_seconds*1000)break;publish_status(0);}
 result=(io_errors||adapter_errors)?22:!active_adapters?22:0;
finish:
 stopping=1;SetEvent(stop_event);
 for(k=0;k<adapter_count;k++)if(adapters[k].thread){WaitForSingleObject(adapters[k].thread,INFINITE);CloseHandle(adapters[k].thread);}
 for(k=0;k<adapter_count;k++)if(adapters[k].opened&&!validate_pcap_file(adapters+k))io_errors++;
 if(packet_log!=INVALID_HANDLE_VALUE){if(!FlushFileBuffers(packet_log))io_errors++;CloseHandle(packet_log);packet_log=INVALID_HANDLE_VALUE;}
 if(adapter_log!=INVALID_HANDLE_VALUE){if(!FlushFileBuffers(adapter_log))io_errors++;CloseHandle(adapter_log);adapter_log=INVALID_HANDLE_VALUE;}
 if(!result&&(io_errors||adapter_errors))result=22;
 publish_status(0);publish_status(1);if(!result&&status_errors)result=22;SetConsoleCtrlHandler(console_ctrl,FALSE);CloseHandle(stop_event);stop_event=NULL;DeleteCriticalSection(&state_lock);CloseHandle(capture_mutex);return result;
}
void WINAPI capture_entry(void){int argc=0,result=2;WCHAR **argv=CommandLineToArgvW(GetCommandLineW(),&argc);
 if(argv){if(argc>=2&&wcscmp(argv[1],L"--probe")==0){if(argc<=3)result=probe(argc==3?argv[2]:NULL);}else result=capture_run(argc,argv);LocalFree(argv);}ExitProcess((UINT)result);
}
