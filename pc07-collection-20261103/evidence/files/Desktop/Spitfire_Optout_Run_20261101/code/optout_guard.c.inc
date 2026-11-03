#ifndef CALG_SHA_256
#define CALG_SHA_256 0x0000800c
#endif
/* Read-only state guard for exactly the independently verified original image.
 * No WriteProcessMemory, remote threads, or DLL injection are used.
 */
static const char expected_original_sha256[]="8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b";
static int original_sha256(char hex[65],DWORD*error){HCRYPTPROV provider=0;HCRYPTHASH hash=0;HANDLE file=INVALID_HANDLE_VALUE;static BYTE buffer[8192];BYTE digest[32];DWORD got=0,size=32;int i,ok=0;const char*digits="0123456789abcdef";hex[0]=0;*error=0;
 if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&!CryptAcquireContextW(&provider,NULL,L"Microsoft Enhanced RSA and AES Cryptographic Provider (Prototype)",PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&!CryptAcquireContextW(&provider,NULL,L"Microsoft Enhanced RSA and AES Cryptographic Provider",PROV_RSA_AES,CRYPT_VERIFYCONTEXT)){*error=GetLastError();goto done;}
 if(!CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)){*error=GetLastError();goto done;}
 file=CreateFileW(original_path_w,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);if(file==INVALID_HANDLE_VALUE){*error=GetLastError();goto done;}
 for(;;){if(!ReadFile(file,buffer,sizeof(buffer),&got,NULL)){*error=GetLastError();goto done;}if(!got)break;if(!CryptHashData(hash,buffer,got,0)){*error=GetLastError();goto done;}}
 if(!CryptGetHashParam(hash,HP_HASHVAL,digest,&size,0)||size!=32){*error=GetLastError();goto done;}for(i=0;i<32;i++){hex[2*i]=digits[digest[i]>>4];hex[2*i+1]=digits[digest[i]&15];}hex[64]=0;ok=!strcmp(hex,expected_original_sha256);
 done:if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);return ok;
}
static int original_state(const char*leaf,int*optout,int*access){DWORD error=0;char hash[65];HANDLE process=NULL,snapshot=INVALID_HANDLE_VALUE;MODULEENTRY32W module;SIZE_T bytes=0;int ok=0,hash_ok=0,base_ok=0;FILE*f;hash[0]=0;*optout=-1;*access=-1;
 if(original_exact_count!=1||original_foreign||!original_pid){error=ERROR_NOT_FOUND;goto done;}
 hash_ok=original_sha256(hash,&error);if(!hash_ok)goto done;
 snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,original_pid);if(snapshot==INVALID_HANDLE_VALUE){error=GetLastError();goto done;}ZeroMemory(&module,sizeof(module));module.dwSize=sizeof(module);if(!Module32FirstW(snapshot,&module)){error=GetLastError();goto done;}
 base_ok=!_wcsicmp(module.szExePath,original_path_w)&&(uintptr_t)module.modBaseAddr==0x400000u;if(!base_ok){error=ERROR_INVALID_ADDRESS;goto done;}
 process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,original_pid);if(!process){error=GetLastError();goto done;}
 if(!ReadProcessMemory(process,(LPCVOID)(uintptr_t)0x4141D0,optout,sizeof(*optout),&bytes)||bytes!=sizeof(*optout)){error=GetLastError();goto done;}
 if(!ReadProcessMemory(process,(LPCVOID)(uintptr_t)0x416DEC,access,sizeof(*access),&bytes)||bytes!=sizeof(*access)){error=GetLastError();goto done;}
 ok=(*optout==0||*optout==1)&&*access>=0&&*access<=3;
 done:if(process)CloseHandle(process);if(snapshot!=INVALID_HANDLE_VALUE)CloseHandle(snapshot);f=openout(leaf,"wb");if(f){fprintf(f,"{\"pid\":%lu,\"read_only\":true,\"expected_sha256\":",(unsigned long)original_pid);js(f,expected_original_sha256);fputs(",\"actual_sha256\":",f);js(f,hash);fprintf(f,",\"hash_matches\":%s,\"base_matches_0x400000\":%s,\"state_valid\":%s,\"emp_optout\":%d,\"gAccessLevel\":%d,\"win32_error\":%lu}\n",hash_ok?"true":"false",base_ok?"true":"false",ok?"true":"false",*optout,*access,(unsigned long)error);fclose(f);}return ok;
}
