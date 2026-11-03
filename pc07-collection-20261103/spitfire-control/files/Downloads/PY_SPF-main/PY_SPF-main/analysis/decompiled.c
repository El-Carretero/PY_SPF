
/* ===== _Add_String_Answer_from_Command @ 00405cc2 ===== */

void __cdecl _Add_String_Answer_from_Command(char *param_1)

{
  char cVar1;
  int local_e4;
  int local_dc;
  size_t local_d8;
  char local_d4 [200];
  size_t local_c;
  int local_8;
  
  DAT_00434c88 = DAT_00434c88 + 1;
  local_c = _strlen(param_1);
  local_e4 = 1;
  _sprintf(local_d4,s___u__u__00434d00,DAT_00434c88,1);
  local_d8 = _strlen(local_d4);
  local_dc = 0;
  for (local_8 = 0; local_8 < (int)local_c; local_8 = local_8 + 1) {
    cVar1 = param_1[local_8];
    if (((cVar1 == '\r') || (cVar1 == '\n')) || (cVar1 == '\0')) {
      if (local_dc != 0) {
        local_d4[local_d8] = '\0';
        _gextHandleReceivedMsg(local_d4);
        local_e4 = local_e4 + 1;
        _sprintf(local_d4,s___u__u__00434cf8,DAT_00434c88,local_e4);
        local_d8 = _strlen(local_d4);
        local_dc = 0;
      }
    }
    else {
      if ((int)local_d8 < 0xc6) {
        local_d4[local_d8] = cVar1;
        local_d8 = local_d8 + 1;
      }
      local_dc = local_dc + 1;
    }
  }
  if (local_dc != 0) {
    local_d4[local_d8] = '\0';
    _gextHandleReceivedMsg(local_d4);
  }
  return;
}



/* ===== _BW_reset @ 0040f0b7 ===== */

undefined4 __cdecl _BW_reset(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 3) {
    _sprintf(&_g_par_str,&DAT_00436b34);
    _push_inside_stack(0x7e2);
    _push_inside_stack(0x42a);
  }
  return 0;
}



/* ===== _CalcCrc16 @ 00404d45 ===== */

int __cdecl _CalcCrc16(char *param_1,ushort param_2)

{
  char *pcVar1;
  short local_c;
  
  while( true ) {
    pcVar1 = param_1 + 1;
    if (*param_1 == 0) break;
    param_2 = param_2 ^ (short)*param_1 << 8;
    for (local_c = 0; param_1 = pcVar1, local_c < 8; local_c = local_c + 1) {
      if (((int)(short)param_2 & 0x8000U) == 0) {
        param_2 = param_2 << 1;
      }
      else {
        param_2 = param_2 << 1 ^ 0x1021;
      }
    }
  }
  return (int)(short)param_2;
}



/* ===== _CalculateBlockCRC16 @ 0040544e ===== */

uint __cdecl _CalculateBlockCRC16(int param_1,ushort param_2,byte *param_3)

{
  byte *local_8;
  
  local_8 = param_3;
  while (param_1 != 0) {
    param_2 = param_2 << 8 ^
              *(ushort *)(&DAT_0043438c + ((int)(uint)param_2 >> 8 ^ (uint)*local_8) * 2);
    param_1 = param_1 + -1;
    local_8 = local_8 + 1;
  }
  return (uint)param_2;
}



/* ===== _CalculateBlockCRC32 @ 004055d6 ===== */

uint __cdecl _CalculateBlockCRC32(int param_1,uint param_2,byte *param_3)

{
  byte *local_8;
  
  local_8 = param_3;
  while (param_1 != 0) {
    param_2 = param_2 >> 8 ^ *(uint *)(&_ccitt_32 + ((param_2 ^ *local_8) & 0xff) * 4);
    param_1 = param_1 + -1;
    local_8 = local_8 + 1;
  }
  return param_2;
}



/* ===== _CalculateCharacterCRC16 @ 004054e8 ===== */

uint __cdecl _CalculateCharacterCRC16(ushort param_1,byte param_2)

{
  return ((uint)param_1 << 8 ^
         (uint)*(ushort *)(&DAT_0043438c + ((int)(uint)param_1 >> 8 ^ (uint)param_2) * 2)) & 0xffff;
}



/* ===== _CalculateCharacterCRC16VB @ 00405537 ===== */

uint __cdecl _CalculateCharacterCRC16VB(ushort param_1,byte param_2)

{
  uint uVar1;
  
  uVar1 = _CalculateCharacterCRC16(param_1,param_2);
  return uVar1 & 0xffff;
}



/* ===== _CalculateCharacterCRC16m @ 00405576 ===== */

uint __cdecl _CalculateCharacterCRC16m(ushort param_1,byte param_2)

{
  return ((uint)*(ushort *)(&DAT_0043438c + ((int)(uint)param_1 >> 8 ^ (uint)param_2) * 2) ^
         (uint)param_1 << 8) & 0xffff;
}



/* ===== _CalculateCharacterCRC32 @ 0040566c ===== */

uint __cdecl _CalculateCharacterCRC32(uint param_1,byte param_2)

{
  return param_1 >> 8 ^ *(uint *)(&_ccitt_32 + ((param_1 ^ param_2) & 0xff) * 4);
}



/* ===== _CalculateCharacterCRC32VB @ 004056c5 ===== */

void __cdecl _CalculateCharacterCRC32VB(uint param_1,byte param_2)

{
  _CalculateCharacterCRC32(param_1,param_2);
  return;
}



/* ===== _Ch1_Coarse_Check_Callback @ 00411ab5 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _Ch1_Coarse_Check_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _SetCtrlAttribute(DAT_0041417c,0x2b,0x2dd,_DAT_00436720);
      _SetCtrlAttribute(DAT_0041417c,0x2b,0x2df,2);
    }
    else {
      _SetCtrlAttribute(DAT_0041417c,0x2b,0x2dd,_DAT_00436738);
      _SetCtrlAttribute(DAT_0041417c,0x2b,0x2df,0);
    }
  }
  return 0;
}



/* ===== _Ch2_Coarse_Check_Callback @ 00411b86 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _Ch2_Coarse_Check_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _SetCtrlAttribute(DAT_0041417c,0x2a,0x2dd,_DAT_00436720);
      _SetCtrlAttribute(DAT_0041417c,0x2a,0x2df,2);
    }
    else {
      _SetCtrlAttribute(DAT_0041417c,0x2a,0x2dd,_DAT_00436738);
      _SetCtrlAttribute(DAT_0041417c,0x2a,0x2df,0);
    }
  }
  return 0;
}



/* ===== _Ch3_Coarse_Check_Callback @ 00411d28 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _Ch3_Coarse_Check_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _SetCtrlAttribute(DAT_00414180,0x2a,0x2dd,_DAT_00436720);
      _SetCtrlAttribute(DAT_00414180,0x2a,0x2df,2);
    }
    else {
      _SetCtrlAttribute(DAT_00414180,0x2a,0x2dd,_DAT_00436738);
      _SetCtrlAttribute(DAT_00414180,0x2a,0x2df,0);
    }
  }
  return 0;
}



/* ===== _Ch4_Coarse_Check_Callback @ 00411df9 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _Ch4_Coarse_Check_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _SetCtrlAttribute(DAT_00414180,0x29,0x2dd,_DAT_00436720);
      _SetCtrlAttribute(DAT_00414180,0x29,0x2df,2);
    }
    else {
      _SetCtrlAttribute(DAT_00414180,0x29,0x2dd,_DAT_00436738);
      _SetCtrlAttribute(DAT_00414180,0x29,0x2df,0);
    }
  }
  return 0;
}



/* ===== _CheckInstallationKey @ 0040494b ===== */

int __cdecl _CheckInstallationKey(ushort param_1)

{
  LSTATUS LVar1;
  int iVar2;
  uint uVar3;
  BYTE local_e4 [12];
  CHAR local_d8 [12];
  BYTE local_cc [200];
  
  LVar1 = _ReadRegKeyString(s_software_microsoft_windows_curre_004349e4,s_ueproductid_00434ab6 + 2,
                            local_cc,199);
  if (LVar1 == 0) {
    uVar3 = _CalcCrc16((char *)local_cc,param_1);
    _wsprintfA(local_d8,&DAT_00434b04,uVar3 & 0xffff);
    LVar1 = _ReadRegKeyString(s_software_Spectra_Physics_Sample_A_00434b40,&DAT_00434a7c,local_e4,9)
    ;
    if (LVar1 == 0) {
      iVar2 = _strcmp((char *)local_e4,local_d8);
    }
    else {
      iVar2 = -1;
    }
  }
  else {
    iVar2 = -1;
  }
  return iVar2;
}



/* ===== _ClearScreenCB @ 004065c6 ===== */

undefined4 __cdecl _ClearScreenCB(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _ResetTextBox_12(param_1,4,&DAT_004351c4);
  }
  return 0;
}



/* ===== _CloseServer @ 004060df ===== */

void _CloseServer(void)

{
  if (DAT_00434d6c != 0) {
    _UnregisterTCPServer_4(DAT_00434d68);
  }
  _DiscardPanel_4(DAT_00434d60);
  return;
}



/* ===== _Close_Programmer_Panel_Callback @ 00412f36 ===== */

undefined4 __cdecl
_Close_Programmer_Panel_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_004141a0);
  }
  return 0;
}



/* ===== _Close_UDP_Port @ 0040575f ===== */

undefined4 _Close_UDP_Port(void)

{
  _UDPClose(_Glb_udpHandle);
  return 0;
}



/* ===== _Cnv_IP_Addr_ASCII_Bin32 @ 00404be1 ===== */

uint __cdecl _Cnv_IP_Addr_ASCII_Bin32(int param_1)

{
  char cVar1;
  uint uVar2;
  int local_14;
  int local_10;
  uint local_8;
  
  local_8 = 0;
  local_14 = 0;
  local_10 = 0;
  do {
    for (; ((cVar1 = *(char *)(local_14 + param_1), cVar1 < '0' || ('9' < cVar1)) && (cVar1 != '\0')
           ); local_14 = local_14 + 1) {
    }
    uVar2 = _atoi((char *)(local_14 + param_1));
    if (0xff < uVar2) {
      return 0xffffffff;
    }
    local_8 = local_8 >> 8 | uVar2 << 0x18;
    do {
      cVar1 = *(char *)(local_14 + param_1);
      if ((cVar1 < '0') || ('9' < cVar1)) break;
      local_14 = local_14 + 1;
    } while (cVar1 != '\0');
    local_10 = local_10 + 1;
    if (3 < local_10) {
      return local_8;
    }
  } while( true );
}



/* ===== _DivisorCallback @ 0040e75f ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _DivisorCallback(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_18;
  float local_14;
  float local_10;
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414180,0x2b,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d54,(double)local_8);
    _push_inside_stack(0x7e4);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (_DAT_00436748 == local_c) {
      _GetCtrlVal_12(DAT_00414180,0x2b,&local_18);
      _GetCtrlVal_12(DAT_0041418c,9,&local_14);
      _GetCtrlVal_12(DAT_00414180,0x1c,&local_10);
      if (_DAT_00436748 == local_18) {
        local_18 = _DAT_00436768;
      }
      if (_DAT_00436748 <= local_10) {
        _SetCtrlVal(DAT_0041417c,6,(double)(local_10 / local_18));
      }
      else {
        _SetCtrlVal(DAT_0041417c,6,(double)local_10);
      }
      if (_DAT_00436748 <= local_14) {
        _SetCtrlVal(DAT_0041417c,7,(double)(local_14 / local_18));
      }
      else {
        _SetCtrlVal(DAT_0041417c,7,(double)local_14);
      }
    }
    else {
      _push_inside_stack(0x401);
    }
  }
  return 0;
}



/* ===== _FlushUDP @ 00405839 ===== */

void _FlushUDP(void)

{
  _Glb_Pointer_UDP_Packet = 0;
  return;
}



/* ===== _GetInstallationKey @ 00404a28 ===== */

int __cdecl _GetInstallationKey(ushort param_1)

{
  LSTATUS LVar1;
  int iVar2;
  BYTE local_cc [200];
  
  LVar1 = _ReadRegKeyString(s_software_microsoft_windows_curre_004349b8,s__productid_00434aab + 1,
                            local_cc,199);
  if (LVar1 == 0) {
    iVar2 = _CalcCrc16((char *)local_cc,param_1);
    iVar2 = (int)(short)iVar2;
  }
  else {
    iVar2 = -1;
  }
  return iVar2;
}



/* ===== _GetPrivateProfileString_1 @ 00404909 ===== */

void __cdecl
_GetPrivateProfileString_1
          (LPCSTR param_1,LPCSTR param_2,LPCSTR param_3,LPSTR param_4,DWORD param_5,LPCSTR param_6)

{
  _GetPrivateProfileStringA_24(param_1,param_2,param_3,param_4,param_5,param_6);
  return;
}



/* ===== _HV_switch @ 0040ec0f ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _HV_switch(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,&DAT_00436b38);
      _push_inside_stack(0x7e0);
      _push_inside_stack(0x425);
    }
    else {
      _sprintf(&_g_par_str,&DAT_00436b3c);
      _push_inside_stack(0x7e1);
      _push_inside_stack(0x425);
    }
  }
  return 0;
}



/* ===== _InitServer @ 00405f08 ===== */

undefined4 __cdecl _InitServer(undefined4 param_1)

{
  int iVar1;
  undefined4 *puVar2;
  undefined4 *puVar3;
  undefined4 local_104 [64];
  
  puVar2 = &DAT_00434d70;
  puVar3 = local_104;
  for (iVar1 = 0x40; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  DAT_00434d60 = _LoadPanel_12(0,s_arserver_uir_00435196 + 2,1);
  if (-1 < DAT_00434d60) {
    DAT_00434d68 = param_1;
    _SetWaitCursor_4(1);
    iVar1 = _RegisterTCPServer_12(param_1,_ServerTCPCB,0);
    if (iVar1 < 0) {
      _MessagePopup_8(s_TCP_Server_004351a3 + 1,s__deServer_registration_failed__004351d1 + 3);
    }
    else {
      DAT_00434d6c = 1;
      _SetWaitCursor_4(0);
      _SetCtrlVal(DAT_00434d60,6,1);
      DAT_00434d64 = _GetTCPHostAddr_8(local_104,0x100);
      if (DAT_00434d64 < 0) {
        FUN_00406621();
      }
      else {
        _SetCtrlVal(DAT_00434d60,0xb,local_104);
        DAT_00434d64 = _GetTCPHostName_8(local_104,0x100);
        if (-1 < DAT_00434d64) {
          _SetCtrlVal(DAT_00434d60,10,local_104);
          _SetCtrlAttribute(DAT_00434d60,3,500,1);
          _SetCtrlVal(DAT_00434d60,5,0);
          return 0;
        }
        FUN_00406621();
      }
      if (DAT_00434d6c != 0) {
        _UnregisterTCPServer_4(param_1);
      }
    }
    return 0;
  }
  return 0xffffffff;
}



/* ===== _LBOstabilitybreak @ 00412695 ===== */

undefined4 __cdecl _LBOstabilitybreak(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_c;
  undefined4 local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,&DAT_004368d8,local_8);
    _push_inside_stack(0x7ff);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (local_c != 0) {
      _push_inside_stack(0x436);
    }
  }
  return 0;
}



/* ===== _LSB @ 00407fa4 ===== */

undefined1 __cdecl _LSB(undefined1 param_1)

{
  return param_1;
}



/* ===== _MSB @ 00407fb6 ===== */

uint __cdecl _MSB(uint param_1)

{
  return param_1 >> 8;
}



/* ===== _MainCallBack @ 0040b6c4 ===== */

undefined4 __cdecl _MainCallBack(undefined4 param_1,int param_2,undefined4 param_3,uint param_4)

{
  size_t sVar1;
  int iVar2;
  undefined4 *puVar3;
  char *pcVar4;
  char local_68 [80];
  CHAR local_18 [12];
  int local_c;
  uint local_8;
  
  puVar3 = &DAT_004366c8;
  pcVar4 = local_68;
  for (iVar2 = 0x14; iVar2 != 0; iVar2 = iVar2 + -1) {
    *(undefined4 *)pcVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    pcVar4 = pcVar4 + 4;
  }
  if (param_2 == 7) {
    local_8 = param_4 & 0xff;
    local_c = 0;
    do {
      if (local_8 == (int)local_68[*(int *)(&DAT_004366b8 + local_c * 4) + local_c * 0x14]) {
        *(int *)(&DAT_004366b8 + local_c * 4) = *(int *)(&DAT_004366b8 + local_c * 4) + 1;
        iVar2 = local_c * 4;
        sVar1 = _strlen(local_68 + local_c * 0x14);
        if (*(size_t *)(&DAT_004366b8 + iVar2) == sVar1) {
          _GetPrivateProfileString_1
                    (s_Spitfire_00436db7 + 1,s_maxLevel_00436e3f + 1,&DAT_00436ed4,local_18,9,
                     s_inc__config_sp_00436ed6 + 2);
          switch(local_c) {
          case 0:
          case 1:
            _SetAccessLevel(local_c);
            *(undefined4 *)(&DAT_004366b8 + local_c * 4) = 0;
            break;
          case 2:
            iVar2 = _atoi(local_18);
            if ((iVar2 == 0x186b) || (iVar2 = _atoi(local_18), iVar2 == 0xc4a)) {
              _SetAccessLevel(local_c);
              *(undefined4 *)(&DAT_004366b8 + local_c * 4) = 0;
            }
            break;
          case 3:
            iVar2 = _atoi(local_18);
            if (iVar2 == 0xc4a) {
              _SetAccessLevel(local_c);
              *(undefined4 *)(&DAT_004366b8 + local_c * 4) = 0;
            }
          }
        }
      }
      else {
        *(undefined4 *)(&DAT_004366b8 + local_c * 4) = 0;
      }
      local_c = local_c + 1;
    } while (local_c < 4);
  }
  return 0;
}



/* ===== _MainPanelCB @ 004065f8 ===== */

undefined4 __cdecl _MainPanelCB(undefined4 param_1,int param_2)

{
  if (param_2 == 0xb) {
    _HidePanel_4(DAT_00434d60);
  }
  return 0;
}



/* ===== _Monitor_switch @ 00412ffd ===== */

undefined4 __cdecl _Monitor_switch(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined4 local_8;
  
  _GetCtrlVal_12(param_1,param_2,&local_8);
  if (param_3 == 1) {
    _sprintf(&_g_par_str,&DAT_004367f0,local_8);
    _push_inside_stack(0x803);
  }
  return 0;
}



/* ===== _Open_Udp_Port @ 0040577b ===== */

void __cdecl _Open_Udp_Port(undefined4 param_1)

{
  char *pcVar1;
  char local_d0 [200];
  int local_8;
  
  DAT_00434c74 = param_1;
  local_8 = _UDPOpen((short)param_1,&_Glb_udpHandle);
  if (local_8 != 0) {
    pcVar1 = _UDPErrorString(local_8);
    _sprintf(local_d0,s_u_UDPOpen_returned_error_code__d_00434cce + 2,local_8,pcVar1);
    _MessagePopup_8(s_Error_opening_first_UDP_00434d08,local_d0);
  }
  return;
}



/* ===== _Open_Udp_Port2 @ 004057ff ===== */

int __cdecl _Open_Udp_Port2(undefined4 param_1)

{
  int iVar1;
  
  DAT_00434c74 = param_1;
  iVar1 = _UDPOpen((short)param_1,&_Glb_udpHandle);
  return iVar1;
}



/* ===== _Process_Sleep @ 004048f8 ===== */

void __cdecl _Process_Sleep(DWORD param_1)

{
  _Sleep_4(param_1);
  return;
}



/* ===== _QuitProgram @ 0040ab10 ===== */

undefined4 __cdecl _QuitProgram(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _QuitUserInterface_4(0);
  }
  return 0;
}



/* ===== _ReadRegKeyString @ 00404a98 ===== */

LSTATUS __cdecl _ReadRegKeyString(LPCSTR param_1,LPCSTR param_2,LPBYTE param_3,DWORD param_4)

{
  DWORD local_14;
  DWORD local_10;
  HKEY local_c;
  LSTATUS local_8;
  
  local_10 = param_4;
  local_14 = 1;
  local_8 = _RegOpenKeyExA_20((HKEY)&DAT_80000002,param_1,0,0x20019,&local_c);
  if (local_8 == 0) {
    local_8 = _RegQueryValueExA_24(local_c,param_2,(LPDWORD)0x0,&local_14,param_3,&local_10);
    local_8 = _RegCloseKey_4(local_c);
  }
  return local_8;
}



/* ===== _SYNC_Coarse_Check_Callback @ 00411c57 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SYNC_Coarse_Check_Callback(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _SetCtrlAttribute(DAT_0041417c,0x29,0x2dd,_DAT_00436720);
      _SetCtrlAttribute(DAT_0041417c,0x29,0x2df,2);
    }
    else {
      _SetCtrlAttribute(DAT_0041417c,0x29,0x2dd,_DAT_00436738);
      _SetCtrlAttribute(DAT_0041417c,0x29,0x2df,0);
    }
  }
  return 0;
}



/* ===== _ServerTCPCB @ 00406227 ===== */

undefined4 __cdecl _ServerTCPCB(int param_1,int param_2)

{
  int iVar1;
  undefined4 *puVar2;
  char *pcVar3;
  undefined1 local_128 [32];
  int local_108;
  char local_104 [256];
  
  puVar2 = &DAT_00435070;
  pcVar3 = local_104;
  for (iVar1 = 0x40; iVar1 != 0; iVar1 = iVar1 + -1) {
    *(undefined4 *)pcVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    pcVar3 = pcVar3 + 4;
  }
  local_108 = 0xff;
  if (param_2 == 1) {
    if (DAT_00414168 == 0) {
      DAT_00414168 = param_1;
      _SetCtrlVal(DAT_00434d60,5,1);
      DAT_00434d64 = _GetTCPPeerAddr_12(DAT_00414168,local_128,0x1f);
      if (DAT_00434d64 < 0) {
        FUN_00406621();
      }
      else {
        _SetCtrlVal(DAT_00434d60,9,local_128);
        DAT_00434d64 = _GetTCPPeerName_12(DAT_00414168,local_104,0x100);
        if (DAT_00434d64 < 0) {
          FUN_00406621();
        }
        else {
          _SetCtrlVal(DAT_00434d60,8,local_104);
          _sprintf(local_104,s____New_connection_from__s____00435170,local_128);
          _SetCtrlVal(DAT_00434d60,4,local_104);
          _SetCtrlAttribute(DAT_00434d60,3,500,0);
          DAT_00434d64 = _SetTCPDisconnectMode_8(DAT_00414168,0);
          if (DAT_00434d64 < 0) {
            FUN_00406621();
          }
        }
      }
    }
    else {
      DAT_00434d64 = _GetTCPPeerAddr_12(param_1,local_128,0x1f);
      if (DAT_00434d64 < 0) {
        FUN_00406621();
      }
      else {
        _sprintf(local_104,s_1___Refusing_conection_request_f_00435253 + 1,local_128);
        _SetCtrlVal(DAT_00434d60,4,local_104);
        DAT_00434d64 = _DisconnectTCPClient_4(param_1);
        if (DAT_00434d64 < 0) {
          FUN_00406621();
        }
      }
    }
  }
  else if (param_2 == 2) {
    if (param_1 == DAT_00414168) {
      _SetCtrlVal(DAT_00434d60,5,0);
      DAT_00414168 = 0;
      _SetCtrlVal(DAT_00434d60,9,&DAT_004351cc);
      _SetCtrlVal(DAT_00434d60,8,&DAT_004351c8);
      _SetCtrlVal(DAT_00434d60,4,s____Client_disconnected____004351f0);
      _SetCtrlAttribute(DAT_00434d60,3,500,1);
    }
  }
  else if (param_2 == 3) {
    local_108 = _ServerTCPRead_16(DAT_00414168,local_104,0xff,1000);
    if (local_108 < 0) {
      _SetCtrlVal(DAT_00434d60,4,s_PNReceive_Error_004351b2 + 2);
    }
    else {
      local_104[local_108] = '\0';
      _SetCtrlVal(DAT_00434d60,4,local_104);
      _TCP_Parse(local_104);
    }
  }
  return 0;
}



/* ===== _SetAccessLevel @ 0040b0b8 ===== */

void __cdecl _SetAccessLevel(undefined4 param_1)

{
  _gAccessLevel = param_1;
  switch(param_1) {
  case 0:
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x281,s_USER_MODE_00436e24);
    _SetCtrlAttribute(DAT_0041417c,0x31,0x214,0xffffffe2);
    _SetCtrlAttribute(DAT_0041417c,0x31,0x213,0xffffffe2);
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x212,0);
    _SetPanelAttribute(DAT_0041418c,0x21c,0xfa);
    _SetPanelAttribute(DAT_00414180,0x21c,0x1be);
    _SetPanelAttribute(DAT_00414180,0x215,0x186);
    _SetPanelAttribute(DAT_0041417c,0x21c,0x226);
    _SetPanelAttribute(DAT_00414188,0x21c,0xfa);
    _SetPanelAttribute(DAT_00414190,0x23a,0xc0c0c0);
    _SetPanelAttribute(DAT_0041418c,0x23a,0xc0c0c0);
    _SetPanelAttribute(DAT_00414180,0x23a,0xc0c0c0);
    _SetPanelAttribute(DAT_00414188,0x23a,0xc0c0c0);
    _HidePanel_4(DAT_0041419c);
    _HidePanel_4(DAT_004141a0);
    _server_HidePanel();
    break;
  case 1:
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x281,s_SERVICE_MODE__CLICK_TO_LOWER_LEV_00436ee5 + 3);
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x212,1);
    _SetPanelAttribute(DAT_0041418c,0x21c,0x1e0);
    _SetPanelAttribute(DAT_00414180,0x21c,0x1be);
    _SetPanelAttribute(DAT_00414180,0x215,0x2ee);
    _SetPanelAttribute(DAT_0041417c,0x21c,0x226);
    _SetPanelAttribute(DAT_00414188,0x21c,0x1e0);
    _SetPanelAttribute(DAT_00414190,0x23a,0x8000);
    _SetPanelAttribute(DAT_0041418c,0x23a,0x8000);
    _SetPanelAttribute(DAT_00414180,0x23a,0x8000);
    _SetPanelAttribute(DAT_00414188,0x23a,0x8000);
    _DisplayPanel_4(DAT_0041419c);
    _SetPanelAttribute(DAT_0041419c,0x23a,0x8000);
    _HidePanel_4(DAT_004141a0);
    _server_HidePanel();
    break;
  case 2:
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x281,s_FACTORY_MODE__CLICK_TO_LOWER_LEV_00436926 + 2);
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x212,1);
    _SetPanelAttribute(DAT_0041418c,0x21c,0x1e0);
    _SetPanelAttribute(DAT_00414180,0x21c,0x1be);
    _SetPanelAttribute(DAT_00414180,0x215,0x2ee);
    _SetPanelAttribute(DAT_0041417c,0x21c,0x226);
    _SetPanelAttribute(DAT_00414188,0x21c,0x1e0);
    _SetPanelAttribute(DAT_00414190,0x23a,0xffff);
    _SetPanelAttribute(DAT_0041418c,0x23a,0xffff);
    _SetPanelAttribute(DAT_00414180,0x23a,0xffff);
    _SetPanelAttribute(DAT_00414188,0x23a,0xffff);
    _DisplayPanel_4(DAT_0041419c);
    _SetPanelAttribute(DAT_0041419c,0x23a,0xffff);
    _HidePanel_4(DAT_004141a0);
    _server_HidePanel();
    break;
  case 3:
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x281,s_PROGRAMMER_MODE__CLICK_TO_LOWER_L_00436ca8);
    _SetCtrlAttribute(DAT_0041417c,0x2d,0x212,1);
    _SetPanelAttribute(DAT_0041418c,0x21c,0x352);
    _SetPanelAttribute(DAT_00414180,0x21c,0x222);
    _SetPanelAttribute(DAT_00414180,0x215,0x2ee);
    _SetPanelAttribute(DAT_0041417c,0x21c,0x226);
    _SetPanelAttribute(DAT_00414188,0x21c,0x1e0);
    _SetPanelAttribute(DAT_00414190,0x23a,0xffff00);
    _SetPanelAttribute(DAT_0041418c,0x23a,0xffff00);
    _SetPanelAttribute(DAT_00414180,0x23a,0xffff00);
    _SetPanelAttribute(DAT_00414188,0x23a,0xffff00);
    _SetPanelAttribute(DAT_0041417c,0x21c,0x3de);
    _DisplayPanel_4(DAT_0041419c);
    _SetPanelAttribute(DAT_0041419c,0x23a,0xffff00);
    _DisplayPanel_4(DAT_004141a0);
    _SetPanelAttribute(DAT_004141a0,0x23a,0xffff00);
    _server_DisplayPanel();
  }
  return;
}



/* ===== _SetCoarseCallback_btn0 @ 00411863 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetCoarseCallback_btn0(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__d__5_2f_00436b9c,0,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436aec);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x41c);
    }
  }
  return 0;
}



/* ===== _SetCoarseCallback_btn1 @ 00411653 ===== */

undefined4 __cdecl _SetCoarseCallback_btn1(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__d__5_2f_00436bc0,1,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436af8);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
  }
  return 0;
}



/* ===== _SetCoarseCallback_btn2 @ 004116f8 ===== */

undefined4 __cdecl _SetCoarseCallback_btn2(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s_2__d__5_2f_00436bb2 + 2,2,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436af4);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
  }
  return 0;
}



/* ===== _SetCoarseCallback_btn3 @ 0041179d ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetCoarseCallback_btn3(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__d__5_2f_00436ba8,3,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436af0);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x417);
    }
  }
  return 0;
}



/* ===== _SetCoarseCallback_btn4 @ 00411929 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetCoarseCallback_btn4(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__d__5_2f_00436b90,4,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436ae8);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x418);
    }
  }
  return 0;
}



/* ===== _SetCoarseCallback_btn5 @ 004119ef ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetCoarseCallback_btn5(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__d__5_2f_00436b84,5,(double)local_8);
    _push_inside_stack(0x7e3);
    _sprintf(&_g_par_str,&DAT_00436ae4);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x419);
    }
  }
  return 0;
}



/* ===== _SetHVCallback1 @ 0040ef87 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetHVCallback1(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d44,(double)local_8);
    _push_inside_stack(0x7e9);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x410);
    }
  }
  return 0;
}



/* ===== _SetHVCallback2 @ 0040f01f ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _SetHVCallback2(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d3c,(double)local_8);
    _push_inside_stack(0x7ea);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x411);
    }
  }
  return 0;
}



/* ===== _Shutdown @ 0040ac11 ===== */

undefined4 __cdecl _Shutdown(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _QuitUserInterface_4(0);
  }
  return 0;
}



/* ===== _SlowProcessSystemEvents @ 00405412 ===== */

void _SlowProcessSystemEvents(void)

{
  DAT_00434388 = DAT_00434388 + 1;
  if ((DAT_00434388 & 0x1ff) == 0) {
    _ProcessSystemEvents_0();
  }
  return;
}



/* ===== _TCP_Parse @ 00412724 ===== */

void __cdecl _TCP_Parse(char *param_1)

{
  size_t sVar1;
  int iVar2;
  undefined8 uVar3;
  undefined4 uVar4;
  undefined4 local_488;
  float local_484;
  float local_480;
  float local_47c;
  float local_478;
  float local_474 [2];
  uint local_46c;
  float local_468;
  float local_464;
  float local_460;
  float local_45c;
  float local_458;
  int local_454;
  char local_450 [100];
  char local_3ec [1000];
  
  sVar1 = _strlen(param_1);
  if (sVar1 != 0) {
    sVar1 = _strlen(param_1);
    if (param_1[sVar1 - 1] == '\r') {
      sVar1 = _strlen(param_1);
      param_1[sVar1 - 1] = '\0';
    }
    sVar1 = _strlen(param_1);
    if (sVar1 != 0) {
      sVar1 = _strlen(param_1);
      if (param_1[sVar1 - 1] == '\n') {
        sVar1 = _strlen(param_1);
        param_1[sVar1 - 1] = '\0';
      }
      sVar1 = _strlen(param_1);
      if (sVar1 != 0) {
        iVar2 = _strcmp(param_1,s_FAULTS__00436c06 + 2);
        if (iVar2 == 0) {
          _GetCtrlAttribute_16();
          _sprintf(local_3ec,&DAT_00436cf0);
          _Write_to_TCP_Server(local_3ec);
        }
        iVar2 = _strcmp(param_1,s__IDN__00436e98);
        if (iVar2 == 0) {
          _strcpy(local_3ec,s_0Spectra_Physics__Spitfire__0__00436f2b + 1);
          _GetCtrlVal_12(DAT_00414194,0x10);
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_004368d4);
          uVar3 = CONCAT44(local_450,6);
          uVar4 = DAT_00414194;
          _GetCtrlVal_12();
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_004368d0);
          _GetCtrlVal_12(DAT_00414194,7,local_450,uVar4,uVar3);
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_004368cc);
          uVar3 = CONCAT44(local_450,5);
          uVar4 = DAT_00414194;
          _GetCtrlVal_12();
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_004368c8);
          _GetCtrlVal_12(DAT_00414194,4,local_450,uVar4,uVar3);
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_004368c4);
          _GetCtrlVal_12(DAT_00414194,3,local_450);
          _strcat(local_3ec,local_450);
          _strcat(local_3ec,&DAT_00436c04);
          _Write_to_TCP_Server(local_3ec);
        }
        iVar2 = _strcmp(param_1,s_TDG_STATUS__00436c6c);
        if (iVar2 == 0) {
          _GetCtrlVal_12(DAT_0041417c,0x2b,&local_458);
          uVar3 = CONCAT44(&local_45c,0x2a);
          uVar4 = DAT_0041417c;
          _GetCtrlVal_12();
          _GetCtrlVal_12(DAT_00414180,0x2a,&local_460,uVar4,uVar3);
          uVar3 = CONCAT44(&local_464,0x29);
          uVar4 = DAT_00414180;
          _GetCtrlVal_12();
          _GetCtrlVal_12(DAT_0041417c,0x29,&local_468,uVar4,uVar3);
          _GetCtrlAttribute_16(DAT_0041417c,5,500,&local_46c);
          local_46c = (uint)(local_46c == 0);
          _GetCtrlVal_12(DAT_00414180,7,local_474);
          _sprintf(local_3ec,s____3f____3f____3f____3f____3f____00436e49 + 3,(double)local_458,
                   (double)local_45c,(double)local_460,(double)local_464,(double)local_468,local_46c
                   ,(double)local_474[0]);
          _Write_to_TCP_Server(local_3ec);
        }
        iVar2 = _strcmp(param_1,s_TEMP_STATUS__00436843 + 1);
        if (iVar2 == 0) {
          _GetCtrlVal_12(DAT_0041418c,8,&local_478);
          uVar3 = CONCAT44(&local_47c,2);
          uVar4 = DAT_0041418c;
          _GetCtrlVal_12();
          _GetCtrlVal_12(DAT_0041419c,0xf,&local_480,uVar4,uVar3);
          uVar3 = CONCAT44(&local_484,9);
          uVar4 = DAT_0041418c;
          _GetCtrlVal_12();
          _GetCtrlVal_12(DAT_0041417c,0x1d,&local_454,uVar4,uVar3);
          if (local_454 != 0) {
            local_488 = 0;
          }
          _GetCtrlVal_12(DAT_0041417c,0x1f,&local_454);
          if (local_454 != 0) {
            local_488 = 1;
          }
          _GetCtrlVal_12(DAT_0041417c,0x18,&local_454);
          if (local_454 != 0) {
            local_488 = 2;
          }
          _GetCtrlVal_12(DAT_0041417c,0x19,&local_454);
          if (local_454 != 0) {
            local_488 = 3;
          }
          _GetCtrlVal_12(DAT_0041417c,0x16,&local_454);
          if (local_454 != 0) {
            local_488 = 4;
          }
          _sprintf(local_3ec,s_____3f____3f____3f____3f___d_00436c4d + 3,(double)local_478,
                   (double)local_47c,(double)local_480,(double)local_484,local_488);
          _Write_to_TCP_Server(local_3ec);
        }
      }
    }
  }
  return;
}



/* ===== _TransmitCB @ 0040613a ===== */

undefined4 __cdecl _TransmitCB(undefined4 param_1,undefined4 param_2,int param_3)

{
  size_t sVar1;
  int iVar2;
  undefined4 *puVar3;
  char *pcVar4;
  char local_204 [512];
  
  puVar3 = &DAT_00434e70;
  pcVar4 = local_204;
  for (iVar2 = 0x80; iVar2 != 0; iVar2 = iVar2 + -1) {
    *(undefined4 *)pcVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    pcVar4 = pcVar4 + 4;
  }
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,3,local_204);
    _strcat(local_204,&DAT_004351b0);
    _SetCtrlVal(param_1,2,local_204);
    _SetCtrlVal(param_1,3,&DAT_004351d0);
    sVar1 = _strlen(local_204);
    iVar2 = _ServerTCPWrite_16(DAT_00414168,local_204,sVar1,1000);
    if (iVar2 < 0) {
      _SetCtrlVal(param_1,2,s_NTransmit_Error_0043520b + 1);
    }
  }
  return 0;
}



/* ===== _Try_Receive_UDP @ 00405a44 ===== */

void _Try_Receive_UDP(void)

{
  int iVar1;
  int local_5f0;
  int local_5ec;
  undefined4 local_5e8;
  undefined1 local_5e4 [1500];
  int local_8;
  
  local_5e8 = 0;
  do {
    local_8 = _UDPRead(_Glb_udpHandle,local_5e4,0x5d7,1000,&local_5ec);
    if (local_8 != 0) {
      return;
    }
    DAT_00434c84 = DAT_00434c84 + 1;
    local_5e4[local_5ec] = 0;
    iVar1 = local_5ec;
    while ((local_5f0 = iVar1 + -1, 0 < local_5f0 &&
           ((local_5e4[iVar1 + -1] == '\r' || (local_5e4[iVar1 + -1] == '\n'))))) {
      local_5e4[iVar1 + -1] = 0;
      iVar1 = local_5f0;
    }
    _UDP_Analyze_Received_Packet((int)local_5e4,local_5ec);
    local_5e8 = local_5e8 + 1;
  } while (local_5e8 < 10);
  return;
}



/* ===== _UDPClose @ 004051ef ===== */

undefined4 __cdecl _UDPClose(undefined4 param_1)

{
  _closesocket_4(param_1);
  return 0;
}



/* ===== _UDPErrorString @ 00405205 ===== */

char * __cdecl _UDPErrorString(int param_1)

{
  char *pcVar1;
  
  if (param_1 == 0x2714) {
    return s_WSAEINTR__00434a70;
  }
  if (0x2714 < param_1) {
    if (param_1 < 0x2733) {
      if (param_1 == 0x2726) {
        return s_WSAEINVAL__00434c40;
      }
      if (param_1 == 0x2728) {
        return s_Not_Enough_Available_Socket_Reso_00434c18;
      }
      if (param_1 < 0x2729) {
        if (param_1 == 0x271d) {
          return s_UWSAEACCES__00434a0f + 1;
        }
        if (param_1 == 0x271e) {
          return s_WSAEFAULT__00434aa0;
        }
      }
      goto switchD_00405264_caseD_2735;
    }
    switch(param_1) {
    case 0x2733:
      pcVar1 = s_WSAEWOULDBLOCK__00434be0;
      break;
    case 0x2734:
    case 0x2747:
      pcVar1 = s_ileAnother_Windows_Socket_Operat_00434b09 + 3;
      break;
    case 0x2736:
      pcVar1 = s_Not_a_Socket__00434a3c;
      break;
    case 0x2738:
      pcVar1 = s_The_data_was_to_large_to_fit_in_t_00434b80;
      break;
    case 0x273d:
      pcVar1 = s_on_WSAEOPNOTSUPP__00434bcd + 3;
      break;
    case 0x2740:
      pcVar1 = s__USocket_address_is_already_in_u_00434a4a + 2;
      break;
    case 0x2742:
      pcVar1 = s_The_network_subsystem_has_failed_00434c4c;
      break;
    case 0x2744:
      pcVar1 = s_WSAENETRESET__00434ac4;
      break;
    case 0x2745:
      pcVar1 = s_The_connection_has_been_aborted_00434a1c;
      break;
    case 0x2746:
      pcVar1 = s_The_connection_was_reset_by_the_r_00434ad4;
      break;
    case 0x2749:
      pcVar1 = s_WSAENOTCONN__00434b70;
      break;
    case 0x274a:
      pcVar1 = s_rmaThe_Socket_has_been_Shutdown__00434a7d + 3;
      break;
    case 0x274c:
      pcVar1 = s_The_connection_timed_out__00434bf0;
      break;
    default:
      if (param_1 == 0x276d) {
        return s__WSANOTINITIALISED__0043498b + 1;
      }
    case 0x2735:
    case 0x2737:
    case 0x2739:
    case 0x273a:
    case 0x273b:
    case 0x273c:
    case 0x273e:
    case 0x273f:
    case 0x2741:
    case 0x2743:
    case 0x2748:
    case 0x274b:
switchD_00405264_caseD_2735:
      pcVar1 = s_FUnknown_System_Error__0043499f + 1;
    }
    return pcVar1;
  }
  if (param_1 == 0) {
    return s_No_Error__00434c0c;
  }
  goto switchD_00405264_caseD_2735;
}



/* ===== _UDPOpen @ 00404e38 ===== */

int __cdecl _UDPOpen(undefined2 param_1,int *param_2)

{
  int iVar1;
  undefined4 local_1b4;
  undefined4 local_1b0;
  int local_1ac;
  undefined1 local_1a8 [400];
  undefined2 local_18;
  undefined2 local_14;
  undefined2 local_12;
  undefined4 local_10;
  
  local_1b0 = 1;
  local_1b4 = 0;
  local_18 = 0x101;
  local_1ac = _WSAStartup_8(0x101,local_1a8);
  if (local_1ac == 0) {
    iVar1 = _socket_12(2,2,0);
    *param_2 = iVar1;
    if (*param_2 == -1) {
      local_1ac = _WSAGetLastError_0();
      _closesocket_4(*param_2);
      _WSACleanup_0();
    }
    else {
      local_14 = 2;
      local_10 = 0;
      local_12 = _htons_4(param_1);
      local_1ac = _bind_12(*param_2,&local_14,0x10);
      if (local_1ac == 0) {
        _ioctlsocket_12(*param_2,0x8004667e,&local_1b4);
        _setsockopt_20(*param_2,0xffff,0x20,&local_1b0,4);
        local_1ac = 0;
      }
      else {
        local_1ac = _WSAGetLastError_0();
        _closesocket_4(*param_2);
        _WSACleanup_0();
      }
    }
  }
  else {
    _WSACleanup_0();
  }
  return local_1ac;
}



/* ===== _UDPOpen_raw_socket @ 00404fad ===== */

int __cdecl _UDPOpen_raw_socket(undefined2 param_1,int *param_2)

{
  int iVar1;
  undefined1 local_1a8 [400];
  undefined2 local_18;
  undefined2 local_14;
  undefined2 local_12;
  undefined4 local_10;
  
  local_18 = 0x101;
  iVar1 = _WSAStartup_8(0x101,local_1a8);
  if (iVar1 == 0) {
    iVar1 = _socket_12(2,2,0);
    *param_2 = iVar1;
    if (*param_2 == -1) {
      iVar1 = _WSAGetLastError_0();
      _closesocket_4(*param_2);
      _WSACleanup_0();
    }
    else {
      _memset(&local_14,0,0x10);
      local_14 = 2;
      local_10 = 0;
      local_12 = _htons_4(param_1);
      iVar1 = _bind_12(*param_2,&local_14,0x10);
      if (iVar1 == 0) {
        iVar1 = 0;
      }
      else {
        iVar1 = _WSAGetLastError_0();
        _closesocket_4(*param_2);
        _WSACleanup_0();
      }
    }
  }
  else {
    _WSACleanup_0();
  }
  return iVar1;
}



/* ===== _UDPRead @ 004050ff ===== */

undefined4 __cdecl
_UDPRead(undefined4 param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4,int *param_5)

{
  int iVar1;
  undefined4 uVar2;
  undefined1 local_18 [16];
  undefined4 local_8;
  
  local_8 = 0x10;
  _setsockopt_20(param_1,0xffff,0x1006,&param_4,4);
  iVar1 = _recvfrom_24(param_1,param_2,param_3,0,local_18,&local_8);
  if (iVar1 < 0) {
    *param_5 = 0;
    uVar2 = _WSAGetLastError_0();
  }
  else {
    *param_5 = iVar1;
    uVar2 = 0;
  }
  return uVar2;
}



/* ===== _UDPWrite @ 00405184 ===== */

undefined4 __cdecl
_UDPWrite(undefined4 param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4,
         undefined2 param_5)

{
  int iVar1;
  undefined4 uVar2;
  undefined2 local_14;
  undefined2 local_12;
  undefined4 local_10;
  
  local_14 = 2;
  local_10 = param_4;
  local_12 = _htons_4(param_5);
  iVar1 = _sendto_24(param_1,param_2,param_3,0,&local_14,0x10);
  if (iVar1 < 0) {
    uVar2 = _WSAGetLastError_0();
  }
  else {
    uVar2 = 0;
  }
  return uVar2;
}



/* ===== _UDP_Analyze_Received_Packet @ 00405b9a ===== */

void __cdecl _UDP_Analyze_Received_Packet(int param_1,int param_2)

{
  size_t _MaxCount;
  int iVar1;
  int local_c;
  int local_8;
  
  local_c = 0;
  for (local_8 = 0; local_8 < param_2; local_8 = local_8 + 1) {
    if (*(char *)(local_8 + param_1) == ':') {
      local_c = local_8 + 1;
      break;
    }
  }
  if (local_c != 0) {
    _MaxCount = _strlen(s_REPLY_ECLIPSE_00434cb0);
    iVar1 = _strncmp((char *)(local_c + param_1),s_d_REPLY_ECLIPSE_00434cbe + 2,_MaxCount);
    if (iVar1 == 0) {
      for (local_8 = local_c; local_8 < param_2; local_8 = local_8 + 1) {
        if (*(char *)(local_8 + param_1) == ':') {
          local_c = local_8 + 1;
          break;
        }
      }
      _Add_String_Answer_from_Command((char *)(local_c + param_1));
    }
  }
  return;
}



/* ===== _UDP_Refresh @ 004056e8 ===== */

void _UDP_Refresh(void)

{
  if (_Glb_Pointer_UDP_Packet != 0) {
    _Glb_Addr_UDP = _Cnv_IP_Addr_ASCII_Bin32(0x434ca4);
    _UDPWrite(_Glb_udpHandle,&_Glb_UDP_Packet_1400,_Glb_Pointer_UDP_Packet,_Glb_Addr_UDP,
              (short)DAT_00434c74);
    _Glb_Pointer_UDP_Packet = 0;
  }
  return;
}



/* ===== _WSACleanup@0 @ 00413160 ===== */

void _WSACleanup_0(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413160. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_116();
  return;
}



/* ===== _WSAGetLastError@0 @ 00413172 ===== */

void _WSAGetLastError_0(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413172. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_111();
  return;
}



/* ===== _WSAStartup@8 @ 0041316c ===== */

void _WSAStartup_8(void)

{
                    /* WARNING: Could not recover jumptable at 0x0041316c. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_115();
  return;
}



/* ===== _WritePrivateProfileString_1 @ 0040492e ===== */

void __cdecl
_WritePrivateProfileString_1(LPCSTR param_1,LPCSTR param_2,LPCSTR param_3,LPCSTR param_4)

{
  _WritePrivateProfileStringA_16(param_1,param_2,param_3,param_4);
  return;
}



/* ===== _WriteRegKeyString @ 00404b33 ===== */

LSTATUS __cdecl _WriteRegKeyString(LPCSTR param_1,BYTE *param_2)

{
  size_t sVar1;
  DWORD local_10;
  HKEY local_c;
  LSTATUS local_8;
  
  local_8 = _RegCreateKeyExA_36((HKEY)&DAT_80000002,param_1,0,(LPSTR)0x0,0,2,
                                (LPSECURITY_ATTRIBUTES)0x0,&local_c,&local_10);
  if (local_8 == 0) {
    sVar1 = _strlen((char *)param_2);
    local_8 = _RegSetValueExA_24(local_c,(LPCSTR)0x0,0,1,param_2,sVar1 + 1);
    local_8 = _RegCloseKey_4(local_c);
  }
  return local_8;
}



/* ===== _WriteString @ 0040e38e ===== */

void __cdecl _WriteString(char *param_1)

{
  int local_204;
  int local_200;
  char local_1fc [500];
  va_list local_8;
  
  local_8 = &stack0x00000008;
  _vsprintf(local_1fc,param_1,local_8);
  if (_gAccessLevel == 3) {
    _GetCtrlVal_12(DAT_0041417c,0x2e,&local_200);
    if (local_200 != 0) {
      _GetNumTextBoxLines_12(DAT_0041417c,0x22,&local_204);
      if (99 < local_204) {
        _DeleteTextBoxLine_12(DAT_0041417c,0x22,99);
      }
      _InsertTextBoxLine_16(DAT_0041417c,0x22,0,local_1fc);
    }
  }
  _WriteToUDP(local_1fc);
  return;
}



/* ===== _WriteToUDP @ 0040584e ===== */

void __cdecl _WriteToUDP(char *param_1)

{
  size_t sVar1;
  int iVar2;
  
  sVar1 = _strlen(param_1);
  if ((int)sVar1 < 0x579) {
    if (0x578 < (int)(_Glb_Pointer_UDP_Packet + sVar1)) {
      (&_Glb_UDP_Packet_1400)[_Glb_Pointer_UDP_Packet] = 10;
      _Glb_Addr_UDP = _Cnv_IP_Addr_ASCII_Bin32(0x434c98);
      _UDPWrite(_Glb_udpHandle,&_Glb_UDP_Packet_1400,_Glb_Pointer_UDP_Packet,_Glb_Addr_UDP,
                (short)DAT_00434c74);
      _Glb_Pointer_UDP_Packet = 0;
    }
    if (_Glb_Pointer_UDP_Packet == 0) {
      _strcpy(&_Glb_UDP_Packet_1400,s_Spectra_Physics_CMD_ECLIPSE__00434d20);
      _Glb_Pointer_UDP_Packet = _strlen(&_Glb_UDP_Packet_1400);
    }
    _strcpy(&_Glb_UDP_Packet_1400 + _Glb_Pointer_UDP_Packet,param_1);
    iVar2 = _Glb_Pointer_UDP_Packet + sVar1;
    _Glb_Pointer_UDP_Packet = iVar2 + 1;
    (&_Glb_UDP_Packet_1400)[iVar2] = 10;
  }
  return;
}



/* ===== _Write_to_TCP_Server @ 0040668c ===== */

void __cdecl _Write_to_TCP_Server(char *param_1)

{
  size_t sVar1;
  char local_7d8 [2000];
  va_list local_8;
  
  local_8 = &stack0x00000008;
  _vsprintf(local_7d8,param_1,local_8);
  sVar1 = _strlen(local_7d8);
  _ServerTCPWrite_16(DAT_00414168,local_7d8,sVar1,2000);
  return;
}



/* ===== _assert_cksum_err @ 0040aa99 ===== */

void _assert_cksum_err(void)

{
  _MessagePopup_8(s_OALERT__004368ff + 1,s_CHECKSUM__004369c8);
  _SetCtrlVal(DAT_00414190,0x1f,1);
  return;
}



/* ===== _bind@12 @ 00413148 ===== */

void _bind_12(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413148. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_2();
  return;
}



/* ===== _bwdduality @ 00410600 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _bwdduality(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_SING_00436c10);
    }
    else {
      _sprintf(&_g_par_str,s_DUAL_00436aa2 + 2);
    }
    _push_inside_stack(0x7f1);
    _sprintf(&_g_par_str,&DAT_00436b2c);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x41e);
    }
  }
  return 0;
}



/* ===== _bwdpolarity @ 00410518 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _bwdpolarity(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_NEG_00436780);
    }
    else {
      _sprintf(&_g_par_str,s_POS_00436ecc);
    }
    _push_inside_stack(0x7f1);
    _sprintf(&_g_par_str,&DAT_00436b30);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x41e);
    }
  }
  return 0;
}



/* ===== _check_if_system_healthy @ 004090fa ===== */

void _check_if_system_healthy(void)

{
  undefined4 uVar1;
  undefined4 local_20;
  undefined4 local_1c;
  undefined4 local_18;
  uint local_14;
  
  local_14 = (uint)(_delay_monitor_status == 0);
  if ((local_14 != _old_on_ready) || (_needs_initialization != 0)) {
    _issue_fault_update_sequence();
    if (local_14 == 0) {
      _SetCtrlAttribute(DAT_0041417c,10,500,1);
      _SetCtrlAttribute(DAT_0041417c,0x17,500,1);
      _SetCtrlAttribute(DAT_0041417c,0x15,500,1);
      _SetCtrlAttribute(DAT_0041417c,0x32,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x32,0x281,s_rrFAULT__CLICK_HERE__0043685a + 2);
      _SetCtrlAttribute(DAT_0041417c,0x32,0x370,0xffff00);
    }
    else {
      _SetCtrlAttribute(DAT_0041417c,10,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x17,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x15,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x32,0x370,0xc0c0c0);
      _SetCtrlAttribute(DAT_0041417c,0x32,500,1);
      _SetCtrlAttribute(DAT_0041417c,0x32,0x281,s_ALL_SYS_OK_00436786 + 2);
    }
    _old_on_ready = local_14;
    _needs_initialization = 0;
  }
  if (((_comm_status_ecu != _last_comm_status_ecu) || (_last_ecu_user != _gAccessLevel)) ||
     (_last_ecu_optout != _ecu_optout)) {
    uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
    if (_gAccessLevel == 0) {
      if (_ecu_optout == 0) {
        _SetMenuBarAttribute(uVar1,8,500,_comm_status_ecu != 0);
      }
      else {
        _SetMenuBarAttribute(uVar1,8,500,1);
      }
    }
    else {
      _SetMenuBarAttribute(uVar1,8,500,0);
    }
    _last_comm_status_ecu = _comm_status_ecu;
    _last_ecu_user = _gAccessLevel;
    _last_ecu_optout = _ecu_optout;
  }
  if ((_comm_status_tdg != _last_comm_status_tdg) || (_last_tdg_user != _gAccessLevel)) {
    uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
    if (_gAccessLevel == 0) {
      _SetMenuBarAttribute(uVar1,7,500,_comm_status_tdg != 0);
    }
    else {
      _SetMenuBarAttribute(uVar1,7,500,0);
    }
    _last_comm_status_tdg = _comm_status_tdg;
    _last_tdg_user = _gAccessLevel;
  }
  if (((_comm_status_mil != _last_comm_status_mil) || (_last_mil_user != _gAccessLevel)) ||
     (_last_hed_optout != _hed_optout)) {
    _GetPanelMenuBar_4(DAT_0041417c);
    if (_gAccessLevel == 0) {
      if ((_comm_status_mil == 0) && (_hed_optout == 0)) {
        local_18 = 0;
      }
      else {
        local_18 = 1;
      }
      _SetCtrlAttribute(DAT_0041417c,3,500,local_18);
      if ((_comm_status_mil == 0) && (_hed_optout == 0)) {
        local_1c = 0;
      }
      else {
        local_1c = 1;
      }
      _SetCtrlAttribute(DAT_0041417c,0x34,500,local_1c);
      if ((_comm_status_mil == 0) && (_hed_optout == 0)) {
        local_20 = 0;
      }
      else {
        local_20 = 1;
      }
      _SetCtrlAttribute(DAT_0041417c,0x33,500,local_20);
    }
    else {
      _SetCtrlAttribute(DAT_0041417c,3,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x34,500,0);
      _SetCtrlAttribute(DAT_0041417c,0x33,500,0);
    }
    _last_comm_status_mil = _comm_status_mil;
    _last_mil_user = _gAccessLevel;
    _last_hed_optout = _hed_optout;
  }
  if (((_comm_status_emp != _last_comm_status_emp) || (_last_emp_user != _gAccessLevel)) ||
     (_last_emp_optout != _emp_optout)) {
    uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
    if ((_comm_status_emp == 0) && (_emp_optout == 0)) {
      local_18 = 0;
    }
    else {
      local_18 = 1;
    }
    _SetCtrlAttribute(DAT_0041417c,0x41,0x212,local_18);
    if (_gAccessLevel == 0) {
      if ((_comm_status_emp == 0) && (_emp_optout == 0)) {
        local_1c = 0;
      }
      else {
        local_1c = 1;
      }
      _SetMenuBarAttribute(uVar1,5,500,local_1c);
    }
    else {
      _SetMenuBarAttribute(uVar1,5,500,0);
    }
    _last_comm_status_emp = _comm_status_emp;
    _last_emp_user = _gAccessLevel;
    _last_emp_optout = _emp_optout;
  }
  return;
}



/* ===== _check_problem_status @ 00406d4f ===== */

void _check_problem_status(void)

{
  _time((time_t *)&_strt_time2);
  if (_strt_time1 + 0x1eU < _strt_time2) {
    _errordetected();
    _reconnect();
  }
  else {
    _SetCtrlVal(DAT_0041417c,0x1e,1);
  }
  if (_strt_time1 + 10U < _strt_time2) {
    _Close_UDP_Port();
    _openandconfigureport();
  }
  return;
}



/* ===== _cleanoutheader @ 00407fc8 ===== */

int _cleanoutheader(void)

{
  bool bVar1;
  int iVar2;
  undefined1 uVar3;
  undefined4 local_14;
  undefined4 local_10;
  
  local_10 = 0;
  local_14 = -1;
  bVar1 = true;
  while (bVar1) {
    _DisableBreakOnLibraryErrors_0();
    iVar2 = _ComRdByte_4(_comport);
    if (iVar2 < 0) {
      _corrupt_msg_cnt = _corrupt_msg_cnt + 1;
    }
    else {
      _corrupt_msg_cnt = 0;
    }
    uVar3 = (undefined1)iVar2;
    if ((-1 < iVar2) && (local_10 == 4)) {
      local_10 = 0;
      DAT_00414450 = uVar3;
      local_14 = iVar2;
    }
    bVar1 = false;
    if ((-1 < iVar2) && (local_10 == 3)) {
      local_10 = 4;
      bVar1 = true;
      DAT_0041444f = uVar3;
    }
    if ((-1 < iVar2) && (local_10 == 2)) {
      local_10 = 3;
      bVar1 = true;
      DAT_0041444e = uVar3;
    }
    if ((iVar2 == 2) && (local_10 == 1)) {
      local_10 = 2;
      bVar1 = true;
      DAT_0041444d = uVar3;
    }
    if ((iVar2 == 0x10) && (local_10 == 0)) {
      local_10 = 1;
      bVar1 = true;
      _g_msg_process = uVar3;
    }
  }
  return local_14;
}



/* ===== _clear_cksum_err @ 0040aacd ===== */

void _clear_cksum_err(void)

{
  _SetCtrlVal(DAT_00414190,0x1f,0);
  return;
}



/* ===== _cllbck @ 0040aba7 ===== */

longlong __fastcall
_cllbck(undefined4 param_1,uint param_2,undefined4 param_3,undefined4 param_4,int param_5)

{
  time_t tVar1;
  
  if (param_5 == 1) {
    _evnt_cmt = 0;
  }
  else if ((param_5 != 2) && (param_5 == 3)) {
    tVar1 = _time((time_t *)&_btn_time1);
    param_2 = (uint)((ulonglong)tVar1 >> 0x20);
    _evnt_cmt = 1;
  }
  return (ulonglong)param_2 << 0x20;
}



/* ===== _cllbckcmd_reset @ 00412428 ===== */

undefined4 __cdecl _cllbckcmd_reset(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _sprintf(&_g_par_str,&DAT_00436ac4);
    _push_inside_stack(0x7fc);
    _sprintf(&_g_par_str,&DAT_00436ac0);
    _push_inside_stack(0x801);
    _sprintf(&_g_par_str,&DAT_00436abc);
    _push_inside_stack(0x804);
    _sprintf(&_g_par_str,&DAT_00436ab8);
    _push_inside_stack(0x802);
    _issue_fault_update_sequence();
  }
  return 0;
}



/* ===== _close_curtain @ 0040b920 ===== */

void _close_curtain(void)

{
  undefined4 uVar1;
  
  uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
  _SetMenuBarAttribute(uVar1,0,500,1);
  _SetCtrlAttribute(DAT_0041417c,0x31,0x212,1);
  _SetCtrlAttribute(DAT_0041417c,0x36,0x212,1);
  return;
}



/* ===== _close_ecu @ 0040ac6e ===== */

undefined4 __cdecl _close_ecu(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_00414188);
  }
  return 0;
}



/* ===== _close_fault @ 004071ef ===== */

undefined4 __cdecl _close_fault(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_00414190);
  }
  return 0;
}



/* ===== _close_help @ 0040aca4 ===== */

undefined4 __cdecl _close_help(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_00414194);
  }
  return 0;
}



/* ===== _close_info @ 00407225 ===== */

undefined4 __cdecl _close_info(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_00414180);
  }
  return 0;
}



/* ===== _close_secrets_emp @ 0041254e ===== */

undefined4 __cdecl _close_secrets_emp(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_0041419c);
  }
  return 0;
}



/* ===== _close_service @ 0040725b ===== */

undefined4 __cdecl _close_service(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_00414184);
  }
  return 0;
}



/* ===== _close_setup @ 0040ac38 ===== */

undefined4 __cdecl _close_setup(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _HidePanel_4(DAT_0041418c);
  }
  return 0;
}



/* ===== _closesocket@4 @ 0041315a ===== */

void _closesocket_4(void)

{
                    /* WARNING: Could not recover jumptable at 0x0041315a. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_3();
  return;
}



/* ===== _cmd_osc_to_meas @ 004124db ===== */

undefined4 __cdecl _cmd_osc_to_meas(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414180,7,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436cfc,(double)local_8);
    _push_inside_stack(0x7fe);
    _push_inside_stack(0x429);
  }
  return 0;
}



/* ===== _cmtRETUSERMODE @ 004106e8 ===== */

undefined4 __cdecl _cmtRETUSERMODE(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _SetAccessLevel(_gAccessLevel + -1);
  }
  return 0;
}



/* ===== _com_motor_speed @ 0040e55b ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _com_motor_speed(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d64,(double)local_8);
    _push_inside_stack(0x7de);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x424);
    }
  }
  return 0;
}



/* ===== _decode_VERS_query_msg @ 00408231 ===== */

void _decode_VERS_query_msg(void)

{
  char local_cc [200];
  
  if (_INFO_OPEN != 0) {
    _sprintf(local_cc,s__s__i__i_00436820,s_Power_supply_firmware_revision__004368a3 + 1,
             (uint)DAT_00414455,(uint)DAT_00414456);
  }
  _V_minor = (uint)DAT_00414455;
  _V_major = (uint)DAT_00414456;
  return;
}



/* ===== _decode_asc @ 00410a65 ===== */

void _decode_asc(void)

{
  int iVar1;
  char *pcVar2;
  int local_70;
  int local_6c;
  char local_68 [100];
  
  pcVar2 = _strstr(&_sbuf,s_NOT_CON_00436cf4);
  if (pcVar2 == (char *)0x0) {
    local_6c = 0;
    local_70 = 0;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ',' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    local_6c = iVar1 + 2;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    _strcpy(&_sbuf_asc,local_68);
  }
  else {
    _strcpy(&_sbuf_asc,&_sbuf);
  }
  return;
}



/* ===== _decode_cop @ 00410c84 ===== */

void _decode_cop(void)

{
  int iVar1;
  char *pcVar2;
  int local_70;
  int local_6c;
  undefined1 local_68 [100];
  
  pcVar2 = _strstr(&_sbuf,s_CONNECTED_00436a96 + 2);
  if (pcVar2 == (char *)0x0) {
    local_6c = 0;
    local_70 = 0;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = 0;
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ',' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = 0;
    local_70 = 0;
    local_6c = iVar1 + 2;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = 0;
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ' ' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      (&_sbuf_cop)[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    (&_sbuf_cop)[local_70] = 0;
  }
  else {
    _strcpy(&_sbuf_cop,&_sbuf);
  }
  return;
}



/* ===== _decode_ecu @ 0041141e ===== */

void _decode_ecu(void)

{
  int iVar1;
  char *pcVar2;
  int local_70;
  int local_6c;
  char local_68 [100];
  
  _sprintf(&_sbuf_ecu,&DAT_00436afc);
  pcVar2 = _strstr(&_sbuf,s_CONNECTED_00436a71 + 3);
  if (pcVar2 == (char *)0x0) {
    local_6c = 0;
    local_70 = 0;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ',' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    local_6c = iVar1 + 2;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    _strcat(&_sbuf_ecu,local_68);
  }
  else {
    _strcpy(&_sbuf_ecu,&_sbuf);
  }
  return;
}



/* ===== _decode_emp @ 00410f25 ===== */

void _decode_emp(void)

{
  int iVar1;
  char *pcVar2;
  int local_70;
  int local_6c;
  char local_68 [100];
  
  _sprintf(&_sbuf_emp,&DAT_00436b04);
  pcVar2 = _strstr(&_sbuf,s_erCONNECTED_00436a8a + 2);
  if (pcVar2 == (char *)0x0) {
    local_6c = 0;
    local_70 = 0;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ',' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    local_6c = iVar1 + 2;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    _strcpy(&_sbuf_emp,local_68);
  }
  else {
    _strcpy(&_sbuf_emp,&_sbuf);
  }
  return;
}



/* ===== _decode_energy_msg @ 004082a9 ===== */

/* WARNING: Removing unreachable block (ram,0x004082f7) */
/* WARNING: Removing unreachable block (ram,0x00408332) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_energy_msg(void)

{
  _SetCtrlVal(DAT_0041417c,5,
              (double)(((float)DAT_00414454 + (float)((uint)DAT_00414453 * 0x100)) / _DAT_00436774))
  ;
  return;
}



/* ===== _decode_faults @ 0040a5c5 ===== */

void _decode_faults(void)

{
  uint uVar1;
  uint uVar2;
  uint uVar3;
  int iVar4;
  int local_28;
  int local_24;
  char local_10 [12];
  
  local_24 = 0;
  local_28 = 0;
  while (((&_emp_fault_str)[local_24] != ' ' && ((&_emp_fault_str)[local_24] != '\0'))) {
    local_10[local_28] = (&_emp_fault_str)[local_24];
    local_28 = local_28 + 1;
    local_24 = local_24 + 1;
  }
  local_10[local_28] = '\0';
  uVar1 = _atoi(local_10);
  local_28 = 0;
  iVar4 = local_24;
  while ((local_24 = iVar4 + 1, (&DAT_00416d65)[iVar4] != ' ' && ((&DAT_00416d65)[iVar4] != '\0')))
  {
    local_10[local_28] = (&DAT_00416d65)[iVar4];
    local_28 = local_28 + 1;
    iVar4 = local_24;
  }
  local_10[local_28] = '\0';
  uVar2 = _atoi(local_10);
  local_28 = 0;
  local_24 = iVar4 + 2;
  while (((&_emp_fault_str)[local_24] != ' ' && ((&_emp_fault_str)[local_24] != '\0'))) {
    local_10[local_28] = (&_emp_fault_str)[local_24];
    local_28 = local_28 + 1;
    local_24 = local_24 + 1;
  }
  local_10[local_28] = '\0';
  uVar3 = _atoi(local_10);
  local_28 = 0;
  iVar4 = local_24;
  while ((local_24 = iVar4 + 1, (&DAT_00416d65)[iVar4] != ' ' && ((&DAT_00416d65)[iVar4] != '\0')))
  {
    local_10[local_28] = (&DAT_00416d65)[iVar4];
    local_28 = local_28 + 1;
    iVar4 = local_24;
  }
  local_10[local_28] = '\0';
  iVar4 = _atoi(local_10);
  _LBO_STAB_FAULT = _atoi(local_10);
  _SetCtrlVal(DAT_00414190,0x12,uVar1 & 0x40);
  _SetCtrlVal(DAT_00414190,0xb,uVar1 & 0x20);
  _SetCtrlVal(DAT_00414190,0x10,uVar1 & 0x10);
  _SetCtrlVal(DAT_00414190,0x18,uVar1 & 8);
  _SetCtrlVal(DAT_00414190,0x19,uVar1 & 2);
  _SetCtrlVal(DAT_00414190,0x20,uVar1 & 1);
  _SetCtrlVal(DAT_00414190,6,uVar2 & 0x80);
  _SetCtrlVal(DAT_00414190,7,uVar2 & 0x40);
  _SetCtrlVal(DAT_00414190,0xd,uVar2 & 0x20);
  _SetCtrlVal(DAT_00414190,0x22,uVar2 & 0x10);
  _SetCtrlVal(DAT_00414190,0x1e,uVar2 & 8);
  _SetCtrlVal(DAT_00414190,0xc,uVar2 & 4);
  _SetCtrlVal(DAT_00414190,0x11,uVar2 & 2);
  _SetCtrlVal(DAT_00414190,0xf,uVar3 & 0x10);
  _SetCtrlVal(DAT_00414190,3,uVar3 & 2);
  _SetCtrlVal(DAT_00414190,0x23,uVar3 & 1);
  _SetCtrlVal(DAT_00414190,2,iVar4);
  _LBO_STABILITY_STATE = iVar4;
  return;
}



/* ===== _decode_passcode_query_msg @ 00409f9c ===== */

/* WARNING: Removing unreachable block (ram,0x0040a3ab) */
/* WARNING: Removing unreachable block (ram,0x0040a303) */
/* WARNING: Removing unreachable block (ram,0x0040a25b) */
/* WARNING: Removing unreachable block (ram,0x0040a1b3) */
/* WARNING: Removing unreachable block (ram,0x0040a10b) */
/* WARNING: Removing unreachable block (ram,0x00409fea) */
/* WARNING: Removing unreachable block (ram,0x0040a025) */
/* WARNING: Removing unreachable block (ram,0x0040a146) */
/* WARNING: Removing unreachable block (ram,0x0040a1ee) */
/* WARNING: Removing unreachable block (ram,0x0040a296) */
/* WARNING: Removing unreachable block (ram,0x0040a33e) */
/* WARNING: Removing unreachable block (ram,0x0040a3e6) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_passcode_query_msg(void)

{
  float fVar1;
  
  fVar1 = ((float)DAT_00414454 + (float)((uint)DAT_00414453 * 0x100)) / _DAT_00436770;
  if (_SETUP_OPEN != 0) {
    _SetCtrlAttribute(DAT_0041418c,2,0x2da,(double)fVar1);
    _SetCtrlAttribute(DAT_0041418c,3,0x2da,(double)fVar1);
    _SetCtrlAttribute(DAT_0041418c,8,0x2da,(double)fVar1);
  }
  _initial_secrets_fill = 0;
  return;
}



/* ===== _decode_ramp_query_msg @ 0040842c ===== */

/* WARNING: Removing unreachable block (ram,0x00408473) */
/* WARNING: Removing unreachable block (ram,0x004084d0) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_ramp_query_msg(void)

{
  char local_d8 [200];
  float local_10;
  float local_c;
  uint local_8;
  
  local_c = (float)(DAT_00414453 & 1);
  local_8 = (uint)DAT_00414455;
  local_10 = (((float)local_8 / _DAT_00436770) * _DAT_00436770) / _DAT_0043676c;
  if (_DAT_00436768 == local_c) {
    _sprintf(local_d8,s_1_s__5_2f__s_00436f0b + 1,s__Softstart__ENABLED__stepsize_004367a2 + 2,
             (double)local_10,&DAT_0043694c);
  }
  else {
    _sprintf(local_d8,&DAT_00436888,s_Softstart__DISABLED_00436990);
  }
  return;
}



/* ===== _decode_rf_msg @ 0040a41d ===== */

/* WARNING: Removing unreachable block (ram,0x0040a456) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_rf_msg(void)

{
  int local_10;
  float local_c;
  uint local_8;
  
  local_8 = (uint)DAT_00414453;
  local_c = (float)local_8;
  _GetNumListItems_12(DAT_0041418c,7,&local_10);
  if ((_DAT_00436748 == local_c) && (local_10 == 3)) {
    _SetCtrlVal(DAT_0041418c,0xb,_DAT_00436740);
  }
  else {
    _SetCtrlVal(DAT_0041418c,7,(double)local_c);
  }
  return;
}



/* ===== _decode_rf_msg_SETUP @ 0040a4f1 ===== */

/* WARNING: Removing unreachable block (ram,0x0040a52a) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_rf_msg_SETUP(void)

{
  uint uVar1;
  byte bVar2;
  int local_8;
  
  bVar2 = DAT_00414453;
  uVar1 = (uint)DAT_00414453;
  _GetNumListItems_12(DAT_0041418c,0xb,&local_8);
  if ((_DAT_00436748 == (float)uVar1) && (local_8 == 3)) {
    _SetCtrlVal(DAT_0041418c,0xb,_DAT_00436740);
  }
  else {
    _SetCtrlVal(DAT_0041418c,0xb,(double)bVar2);
  }
  return;
}



/* ===== _decode_setup_msg_LBO_temp @ 00408379 ===== */

/* WARNING: Removing unreachable block (ram,0x004083c7) */
/* WARNING: Removing unreachable block (ram,0x00408402) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_setup_msg_LBO_temp(void)

{
  return;
}



/* ===== _decode_state_msg @ 0040856c ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _decode_state_msg(void)

{
  float10 fVar1;
  undefined4 local_28;
  undefined4 local_1c;
  float local_14;
  float local_10;
  int local_c;
  undefined4 local_8;
  
  _SetCtrlVal(DAT_0041417c,0x16,DAT_00414468 == '\0');
  if ((DAT_00414468 == '\x01') && (_LBO_STABILITY_STATE == 0)) {
    local_1c = 1;
  }
  else {
    local_1c = 0;
  }
  _SetCtrlVal(DAT_0041417c,0x1f,local_1c);
  local_8 = _GetCtrlVal_12(DAT_00414190,0x1f,&local_c);
  if ((local_c == 0) && (_LBO_STABILITY_STATE == 0)) {
    _SetCtrlVal(DAT_0041417c,0x1d,DAT_00414468 == '\x02');
  }
  else {
    _SetCtrlVal(DAT_0041417c,0x1d,_DAT_00436760);
  }
  _SetCtrlVal(DAT_0041417c,0x18,DAT_00414468 == '\x03');
  local_8 = _GetCtrlVal_12(DAT_0041418c,3,&local_10);
  local_8 = _GetCtrlVal_12(DAT_0041418c,8,&local_14);
  fVar1 = (float10)_fabs((double)(local_10 - local_14));
  if ((fVar1 <= (float10)_DAT_00436878) || (DAT_00414468 != '\0')) {
    local_28 = 0;
  }
  else {
    local_28 = 1;
  }
  _SetCtrlVal(DAT_0041417c,0x19,local_28);
  _SetCtrlVal(DAT_0041417c,0x19,DAT_00414468 == '\0');
  return;
}



/* ===== _decode_tdg @ 0041115a ===== */

void _decode_tdg(void)

{
  int iVar1;
  char *pcVar2;
  int local_70;
  int local_6c;
  char local_68 [100];
  
  _sprintf(&_sbuf_tdg,&DAT_00436b00);
  pcVar2 = _strstr(&_sbuf,s_CONNECTED_00436a7e + 2);
  if (pcVar2 == (char *)0x0) {
    local_6c = 0;
    local_70 = 0;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ',' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    local_6c = iVar1 + 2;
    while (((&_sbuf)[local_6c] != ',' && ((&_sbuf)[local_6c] != '\0'))) {
      local_68[local_70] = (&_sbuf)[local_6c];
      local_70 = local_70 + 1;
      local_6c = local_6c + 1;
    }
    local_68[local_70] = '\0';
    local_70 = 0;
    iVar1 = local_6c;
    while ((local_6c = iVar1 + 1, (&DAT_00414fa1)[iVar1] != ' ' && ((&DAT_00414fa1)[iVar1] != '\0'))
          ) {
      local_68[local_70] = (&DAT_00414fa1)[iVar1];
      local_70 = local_70 + 1;
      iVar1 = local_6c;
    }
    local_68[local_70] = '\0';
    _strcpy(&_sbuf_tdg,local_68);
  }
  else {
    _strcpy(&_sbuf_tdg,&_sbuf);
  }
  return;
}



/* ===== _decode_tdg_stbh @ 0041023e ===== */

void __cdecl _decode_tdg_stbh(uint param_1)

{
  uint uVar1;
  
  uVar1 = param_1 & 0x300000;
  if (uVar1 == 0x200000) {
    _SetCtrlAttribute(DAT_0041417c,5,500,0);
    _SetCtrlAttribute(DAT_0041417c,5,0x281,s__RESET_BWD_00436806 + 2);
    _SetCtrlAttribute(DAT_0041417c,5,0x370,0xffff00);
  }
  else if (uVar1 < 0x200001) {
    if (uVar1 == 0x100000) {
      _SetCtrlAttribute(DAT_0041417c,5,500,0);
      _SetCtrlAttribute(DAT_0041417c,5,0x281,s_RESET_BWD_00436812 + 2);
      _SetCtrlAttribute(DAT_0041417c,5,0x370,0xffff00);
    }
    else if ((uVar1 < 0x100001) && (uVar1 == 0)) {
      _SetCtrlAttribute(DAT_0041417c,5,0x370,0xc0c0c0);
      _SetCtrlAttribute(DAT_0041417c,5,500,1);
      _SetCtrlAttribute(DAT_0041417c,5,0x281,s_BWD_OK_00436f24);
    }
  }
  else if (uVar1 == 0x300000) {
    _SetCtrlAttribute(DAT_0041417c,5,500,0);
    _SetCtrlAttribute(DAT_0041417c,5,0x281,s_eRESET_BWD_004367fb + 1);
    _SetCtrlAttribute(DAT_0041417c,5,0x370,0xffff00);
  }
  _SetCtrlVal(DAT_00414180,0x2f,param_1 & 1);
  _SetCtrlVal(DAT_0041417c,0x1b,(param_1 & 0x10000) == 0);
  _SetCtrlVal(DAT_0041417c,0x1a,(param_1 & 0x20000) == 0);
  return;
}



/* ===== _decode_tdg_stbh_nom @ 00410053 ===== */

void __cdecl _decode_tdg_stbh_nom(uint param_1)

{
  undefined4 local_1c;
  
  _SetCtrlVal(DAT_00414190,0x13,(param_1 & 0x2000) != 0);
  _SetCtrlVal(DAT_00414190,0x17,(param_1 & 0x4000) != 0);
  _SetCtrlVal(DAT_00414190,0xe,(param_1 & 0x1000) != 0);
  _SetCtrlVal(DAT_00414190,0x15,(param_1 & 0x800) != 0);
  _SetCtrlVal(DAT_00414190,0x16,(param_1 & 0x8000) != 0);
  if ((((param_1 & 0x2000) == 0) && ((param_1 & 0x4000) == 0)) && ((param_1 & 0x1000) == 0)) {
    local_1c = 0;
  }
  else {
    local_1c = 1;
  }
  _SetCtrlVal(DAT_0041417c,0xf,local_1c);
  return;
}



/* ===== _decodenum @ 0040fe1e ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

float10 __cdecl _decodenum(int param_1)

{
  float10 fVar1;
  int local_c;
  int local_8;
  
  local_8 = 0;
  local_c = 0;
  while( true ) {
    if ((5 < local_c) || (*(char *)(local_8 + param_1) == '\0')) {
      if (local_c == 6) {
        fVar1 = (float10)_atof(local_8 + param_1);
      }
      else {
        fVar1 = (float10)_DAT_00436728;
      }
      return fVar1;
    }
    if (*(char *)(local_8 + param_1) == ' ') {
      local_c = local_c + 1;
    }
    if (*(char *)(local_8 + param_1) == '\0') break;
    local_8 = local_8 + 1;
  }
  return (float10)_DAT_0043672c;
}



/* ===== _decodenum_del @ 0040e484 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

float10 __cdecl _decodenum_del(int param_1)

{
  float10 fVar1;
  int local_c;
  int local_8;
  
  local_8 = 0;
  local_c = 0;
  while( true ) {
    if ((2 < local_c) || (*(char *)(local_8 + param_1) == '\0')) {
      if (local_c == 3) {
        fVar1 = (float10)_atof(local_8 + param_1);
      }
      else {
        fVar1 = (float10)_DAT_00436728;
      }
      return fVar1;
    }
    if (*(char *)(local_8 + param_1) == ' ') {
      local_c = local_c + 1;
    }
    if (*(char *)(local_8 + param_1) == '\0') break;
    local_8 = local_8 + 1;
  }
  return (float10)_DAT_0043672c;
}



/* ===== _display_faults @ 00412fc2 ===== */

undefined4 __cdecl _display_faults(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _FAULTS_OPEN = 1;
    _DisplayPanel_4(DAT_00414190);
  }
  return 0;
}



/* ===== _displaylen1 @ 004076ac ===== */

int _displaylen1(void)

{
  undefined4 local_c;
  undefined4 local_8;
  
  local_8 = 0;
  if (_fifo1 == 0) {
    local_8 = 0;
  }
  else {
    for (local_c = _fifo1; *(int *)(local_c + 4) != 0; local_c = *(int *)(local_c + 4)) {
      local_8 = local_8 + 1;
    }
  }
  return local_8;
}



/* ===== _displaylen2 @ 00407475 ===== */

int _displaylen2(void)

{
  undefined4 local_c;
  undefined4 local_8;
  
  local_8 = 0;
  if (_fifo2 == 0) {
    local_8 = 0;
  }
  else {
    for (local_c = _fifo2; *(int *)(local_c + 4) != 0; local_c = *(int *)(local_c + 4)) {
      local_8 = local_8 + 1;
    }
  }
  return local_8;
}



/* ===== _dothetango @ 004081a3 ===== */

void _dothetango(void)

{
  if (0 < _g_message_balance_count) {
    _Try_Receive_UDP();
  }
  return;
}



/* ===== _dothewaltz @ 00407848 ===== */

void _dothewaltz(void)

{
  int iVar1;
  
  iVar1 = _displaylen1();
  if (iVar1 == 0) {
    iVar1 = _displaylen2();
    if (iVar1 == 0) {
      _push_usual_auto_updates();
    }
  }
  iVar1 = _displaylen1();
  if ((iVar1 < 1) || (_g_message_balance_count != 0)) {
    iVar1 = _displaylen2();
    if ((0 < iVar1) && (_g_message_balance_count == 0)) {
      _issue_event2();
      _pop2();
      _u_revd = _u_revd + 1;
      _UDP_Refresh();
    }
  }
  else {
    _issue_event1();
    _pop1();
    _u_revd = _u_revd + 1;
    _UDP_Refresh();
  }
  return;
}



/* ===== _ecu_hum_decode @ 004087fe ===== */

void __cdecl _ecu_hum_decode(float param_1)

{
  _SetCtrlVal(DAT_00414188,2,(double)param_1);
  return;
}



/* ===== _ecu_set_temp @ 0040e6be ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _ecu_set_temp(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414188,7,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d5c,(double)local_8);
    _push_inside_stack(0x7e5);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (_DAT_00436748 != local_c) {
      _push_inside_stack(0x408);
    }
  }
  return 0;
}



/* ===== _ecu_stb_decode @ 00408c01 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _ecu_stb_decode(float param_1)

{
  int iVar1;
  uint uVar2;
  undefined4 uVar3;
  undefined1 local_38;
  uint local_20;
  
  if (_ecu_optout == 0) {
    if (param_1 < (float)_DAT_00436750) {
      local_20 = __ftol();
    }
    else {
      iVar1 = __ftol();
      local_20 = iVar1 + 0x80000000;
    }
    uVar2 = _MSB(local_20);
    if (param_1 < (float)_DAT_00436750) {
      uVar3 = __ftol();
      local_38 = (undefined1)uVar3;
    }
    else {
      uVar3 = __ftol();
      local_38 = (undefined1)uVar3;
    }
    _LSB(local_38);
    _comm_status_ecu = uVar2 & 8;
    _SetCtrlVal(DAT_0041417c,0x10,_comm_status_ecu == 0);
    if (_used_comm_status_ecu != _comm_status_ecu) {
      _push_initial_updates_ecu();
      _used_comm_status_ecu = _comm_status_ecu;
    }
  }
  else {
    _comm_status_ecu = 0;
    _SetCtrlVal(DAT_0041417c,0x10,0);
  }
  return;
}



/* ===== _ecu_stbh_decode @ 00409b4e ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _ecu_stbh_decode(float param_1)

{
  byte bVar1;
  int iVar2;
  uint uVar3;
  undefined4 uVar4;
  bool bVar5;
  bool bVar6;
  bool bVar7;
  bool bVar8;
  int local_64;
  int local_60;
  undefined1 local_48;
  uint local_30;
  
  if (param_1 < (float)_DAT_00436750) {
    local_30 = __ftol();
  }
  else {
    iVar2 = __ftol();
    local_30 = iVar2 + 0x80000000;
  }
  uVar3 = _MSB(local_30);
  if (param_1 < (float)_DAT_00436750) {
    uVar4 = __ftol();
    local_48 = (undefined1)uVar4;
  }
  else {
    uVar4 = __ftol();
    local_48 = (undefined1)uVar4;
  }
  bVar1 = _LSB(local_48);
  _SetCtrlVal(DAT_00414188,0xe,(bVar1 & 2) != 0);
  bVar5 = (uVar3 & 1) != 0;
  bVar6 = (uVar3 & 2) != 0;
  bVar7 = (uVar3 & 4) != 0;
  bVar8 = (uVar3 & 8) != 0;
  if ((bVar5) || (bVar6)) {
    local_60 = 0;
  }
  else {
    local_60 = 1;
  }
  _hum_is_grn = local_60;
  if ((bVar7) || (bVar8)) {
    local_64 = 0;
  }
  else {
    local_64 = 1;
  }
  _tem_is_grn = local_64;
  if (bVar5) {
    _SetCtrlVal(DAT_00414188,0xf,_hum_blinkval);
    if (_hum_blinkval == 0) {
      _hum_blinkval = 1;
    }
    else {
      _hum_blinkval = 0;
    }
  }
  else {
    _SetCtrlVal(DAT_00414188,0xf,0);
  }
  if (bVar6) {
    _SetCtrlAttribute(DAT_00414188,0xf,0x399,0xffff00);
  }
  if (_hum_is_grn != 0) {
    _SetCtrlAttribute(DAT_00414188,0xf,0x399,0xff00);
  }
  if (bVar7) {
    _SetCtrlVal(DAT_00414188,0x10,_tem_blinkval);
    if (_tem_blinkval == 0) {
      _tem_blinkval = 1;
    }
    else {
      _tem_blinkval = 0;
    }
  }
  else {
    _SetCtrlVal(DAT_00414188,0x10,0);
  }
  if (bVar8) {
    _SetCtrlAttribute(DAT_00414188,0x10,0x399,0xffff00);
  }
  if (_tem_is_grn != 0) {
    _SetCtrlAttribute(DAT_00414188,0x10,0x399,0xff00);
  }
  return;
}



/* ===== _ecu_stbh_decode_fault @ 004099d9 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _ecu_stbh_decode_fault(float param_1)

{
  byte bVar1;
  int iVar2;
  undefined4 uVar3;
  undefined1 local_38;
  uint local_20;
  
  if (param_1 < (float)_DAT_00436750) {
    local_20 = __ftol();
  }
  else {
    iVar2 = __ftol();
    local_20 = iVar2 + 0x80000000;
  }
  _MSB(local_20);
  if (param_1 < (float)_DAT_00436750) {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  else {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  bVar1 = _LSB(local_38);
  _SetCtrlVal(DAT_00414190,8,(bVar1 & 4) != 0);
  _SetCtrlVal(DAT_00414190,10,(bVar1 & 0x10) != 0);
  return;
}



/* ===== _ecu_stbh_decode_ini @ 00409864 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _ecu_stbh_decode_ini(float param_1)

{
  byte bVar1;
  int iVar2;
  undefined4 uVar3;
  undefined1 local_38;
  uint local_20;
  
  if (param_1 < (float)_DAT_00436750) {
    local_20 = __ftol();
  }
  else {
    iVar2 = __ftol();
    local_20 = iVar2 + 0x80000000;
  }
  _MSB(local_20);
  if (param_1 < (float)_DAT_00436750) {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  else {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  bVar1 = _LSB(local_38);
  _SetCtrlVal(DAT_00414188,8,(bVar1 & 2) != 0);
  _SetCtrlVal(DAT_00414188,0xd,(bVar1 & 0x20) != 0);
  return;
}



/* ===== _ecu_tec_temp_decode @ 00408848 ===== */

void __cdecl _ecu_tec_temp_decode(float param_1)

{
  _SetCtrlVal(DAT_00414188,3,(double)param_1);
  return;
}



/* ===== _ecu_xtal_temp_decode @ 00408823 ===== */

void __cdecl _ecu_xtal_temp_decode(float param_1)

{
  _SetCtrlVal(DAT_00414188,4,(double)param_1);
  return;
}



/* ===== _empower_stb_decode @ 00408d9e ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _empower_stb_decode(float param_1)

{
  byte bVar1;
  int iVar2;
  uint uVar3;
  undefined4 uVar4;
  uint uVar5;
  undefined4 local_60;
  undefined4 local_58;
  int local_54;
  undefined1 local_50;
  uint local_38;
  
  if (_emp_optout == 0) {
    if (param_1 < (float)_DAT_00436750) {
      local_38 = __ftol();
    }
    else {
      iVar2 = __ftol();
      local_38 = iVar2 + 0x80000000;
    }
    uVar3 = _MSB(local_38);
    if (param_1 < (float)_DAT_00436750) {
      uVar4 = __ftol();
      local_50 = (undefined1)uVar4;
    }
    else {
      uVar4 = __ftol();
      local_50 = (undefined1)uVar4;
    }
    bVar1 = _LSB(local_50);
    uVar5 = uVar3 & 2;
    if (((uVar3 & 4) == 0) && (_LBO_STABILITY_STATE != 1)) {
      local_54 = 0;
    }
    else {
      local_54 = 1;
    }
    if (((((bVar1 & 1) == 0) && (uVar5 == 0)) && (local_54 == 0)) && (_LBO_STABILITY_STATE != 1)) {
      local_58 = 1;
    }
    else {
      local_58 = 0;
    }
    _comm_status_emp = uVar3 & 8;
    _SetCtrlVal(DAT_0041417c,0x16,bVar1 & 1);
    _SetCtrlVal(DAT_0041417c,0x1f,local_58);
    _SetCtrlVal(DAT_0041417c,0x1d,local_54);
    _SetCtrlVal(DAT_0041417c,0x18,uVar5);
    _SetCtrlVal(DAT_0041417c,0x19,uVar3 & 1);
    _SetCtrlVal(DAT_0041417c,0x13,_comm_status_emp == 0);
    if (((bVar1 & 1) == 0) && (uVar5 == 0)) {
      local_60 = 0;
    }
    else {
      local_60 = 1;
    }
    _SetCtrlAttribute(DAT_0041417c,0x20,0x212,local_60);
    if (_used_comm_status_emp != _comm_status_emp) {
      _push_initial_updates_emp();
      _used_comm_status_emp = _comm_status_emp;
    }
  }
  else {
    _comm_status_emp = 0;
    _SetCtrlVal(DAT_0041417c,0x13,0);
  }
  return;
}



/* ===== _empoweroptoutcall @ 00411f71 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _empoweroptoutcall(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414188,9,&local_c);
    _sprintf(&_g_par_str,&DAT_004368dc,local_c);
    _push_inside_stack(0x7f4);
    if (local_c == 0) {
      _show_emp_controls();
    }
    else {
      _hide_emp_controls();
    }
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 == local_8) {
      _emp_optout = local_c;
    }
    else {
      _push_inside_stack(0x42c);
    }
  }
  return 0;
}



/* ===== _errordetected @ 00406cdd ===== */

void _errordetected(void)

{
  char local_88 [132];
  
  _SetCtrlVal(DAT_0041417c,0x1e,0);
  _sprintf(local_88,&DAT_00436894,s_Failed_to_connect_to_remote_syst_004369a4);
  if (_pardon_first_time_user == 0) {
    _SetCtrlVal(DAT_0041417c,0x36,local_88);
  }
  return;
}



/* ===== _esc_turnoff @ 00412f64 ===== */

undefined4 __cdecl _esc_turnoff(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 1) {
    _sprintf(&_g_par_str,&DAT_00436ab4);
    _push_inside_stack(0x7ec);
    _SetCtrlVal(DAT_00414188,8,0);
  }
  return 0;
}



/* ===== _exit_from_menu @ 00407291 ===== */

void _exit_from_menu(void)

{
  _Close_UDP_Port();
  _QuitUserInterface_4(0);
  return;
}



/* ===== _firstinline1 @ 0040778b ===== */

undefined4 _firstinline1(void)

{
  undefined4 uVar1;
  
  if (_fifo1 == (undefined4 *)0x0) {
    uVar1 = 0;
  }
  else {
    uVar1 = *_fifo1;
  }
  return uVar1;
}



/* ===== _firstinline2 @ 00407554 ===== */

undefined4 _firstinline2(void)

{
  undefined4 uVar1;
  
  if (_fifo2 == (undefined4 *)0x0) {
    uVar1 = 0;
  }
  else {
    uVar1 = *_fifo2;
  }
  return uVar1;
}



/* ===== _get_tag_title @ 00407f2f ===== */

undefined * __cdecl _get_tag_title(int param_1)

{
  if (param_1 < 2000) {
    _sprintf(&_g_smart,&DAT_00436890,
             s___imp___UP_CheckForDuplicateAppI_0042e020 + param_1 * 0x1e + 0x20);
  }
  else {
    _sprintf(&_g_smart,&DAT_0043688c,
             s___UP_GetTableColumnFromLabel_24_00427580 + param_1 * 0x1e + 0x1c);
  }
  return &_g_smart;
}



/* ===== _gextHandleReceivedMsg @ 0040ba24 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void _gextHandleReceivedMsg(char *param_1)

{
  uint uVar1;
  int iVar2;
  uint uVar3;
  char *pcVar4;
  float10 fVar5;
  uint local_30;
  float local_24;
  float local_20;
  float local_1c;
  int local_18;
  char *local_14;
  uint local_10;
  int local_c;
  float local_8;
  
  if (_gAccessLevel == 3) {
    _time((time_t *)&_stopptime_msg);
    if (10 < (uint)(_stopptime_msg - _starttime_msg)) {
      _SetCtrlVal(DAT_0041417c,0x39);
      _time((time_t *)&_starttime_msg);
      _u_revd = 0;
    }
    _displaylen1();
    _SetCtrlVal(DAT_0041417c,0x38);
    _displaylen2();
    _SetCtrlVal(DAT_0041417c,0x37);
    _GetCtrlVal_12(DAT_0041417c,0x2e);
    if (_DAT_00436748 != local_8) {
      _GetNumTextBoxLines_12(DAT_0041417c,0x21);
      if (99 < local_18) {
        _DeleteTextBoxLine_12(DAT_0041417c,0x21);
      }
      _InsertTextBoxLine_16(DAT_0041417c,0x21,0);
    }
  }
  local_14 = _strtok(param_1,&DAT_00436f18);
  if ((local_14 != (char *)0x0) &&
     (local_14 = _strtok((char *)0x0,&DAT_004367c4), local_14 != (char *)0x0)) {
    local_c = _atoi(local_14);
    local_14 = _strtok((char *)0x0,&DAT_00436b40);
    if (local_14 != (char *)0x0) {
      _strcpy(&_sbuf,local_14);
    }
    _clear_cksum_err();
    if (local_c != 1000) {
      _g_message_balance_count = _g_message_balance_count + -1;
    }
    if (_g_message_balance_count < 0) {
      _g_message_balance_count = 0;
    }
    _refresh_connectivity();
    if (999 < local_c) {
      switch(local_c) {
      case 1000:
        _chars_read = 1;
        break;
      case 0x3e9:
      case 0x3ea:
      case 0x3eb:
      case 0x3ec:
      case 0x3ed:
      case 0x3ee:
      case 0x3f8:
      case 0x3f9:
      case 0x3fc:
      case 0x3fe:
      case 0x3ff:
      case 0x402:
      case 0x403:
      case 0x414:
      case 0x42e:
      case 0x437:
      case 0x439:
      case 0x43b:
        break;
      case 0x3ef:
        _atof();
        _SetCtrlVal();
        break;
      case 0x3f0:
        _atof();
        _SetCtrlVal();
        break;
      case 0x3f1:
        if (_initial_secrets_fill == 0) {
          _atof();
          _SetCtrlVal();
        }
        else {
          _atof();
          _SetCtrlVal();
          _atof();
          _SetCtrlVal();
        }
        break;
      case 0x3f2:
        if (_initial_secrets_fill == 0) {
          _atof();
          _SetCtrlVal();
          _atof();
          _SetCtrlVal();
        }
        else {
          fVar5 = (float10)_atof();
          if ((float10)_DAT_00436730 <= fVar5) {
            _atof();
            _SetCtrlVal();
            _atof();
            _SetCtrlVal();
            _atof();
            _SetCtrlVal();
          }
          else {
            _atof();
            _SetCtrlVal();
            _atof();
            _SetCtrlVal();
            _atof();
            _SetCtrlVal();
          }
          _GetCtrlVal_12(DAT_00414180,0x2b,&local_24);
          _GetCtrlVal_12(DAT_0041418c,9,&local_20);
          _GetCtrlVal_12(DAT_00414180,0x1c,&local_1c);
          if (_DAT_00436748 == local_24) {
            local_24 = _DAT_00436768;
          }
          if (_DAT_00436748 <= local_1c) {
            _SetCtrlVal(DAT_0041417c,6,(double)(local_1c / local_24));
          }
          else {
            _SetCtrlVal(DAT_0041417c,6,(double)local_1c);
          }
          if (_DAT_00436748 <= local_20) {
            _SetCtrlVal(DAT_0041417c,7,(double)(local_20 / local_24));
          }
          else {
            _SetCtrlVal(DAT_0041417c,7,(double)local_20);
          }
        }
        break;
      case 0x3f3:
        if (_initial_secrets_fill == 0) {
          _atof();
          _SetCtrlVal();
        }
        else {
          _atof();
          _SetCtrlVal();
          _atof();
          _SetCtrlVal();
        }
        break;
      case 0x3f4:
        if (_initial_secrets_fill == 0) {
          _atof();
          _SetCtrlVal();
        }
        else {
          _atof();
          _SetCtrlVal();
          _atof();
          _SetCtrlVal();
          _initial_secrets_fill = 0;
        }
        break;
      case 0x3f5:
        fVar5 = (float10)_atof();
        _empower_stb_decode((float)fVar5);
        break;
      case 0x3f6:
        _strcpy(&_emp_fault_str,&_sbuf);
        _decode_faults();
        break;
      case 0x3f7:
        fVar5 = (float10)_atof();
        _mil_stb_decode((float)fVar5);
        _initial_secrets_fill_mil = 0;
        break;
      case 0x3fa:
        _atof();
        _SetCtrlVal();
        break;
      case 0x3fb:
        fVar5 = (float10)_atof();
        _tdg_stb_decode((float)fVar5);
        _initial_secrets_fill_tdg = 0;
        break;
      case 0x3fd:
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414180,0x22,iVar2);
        break;
      case 0x400:
        _atof();
        _SetCtrlVal();
        _GetCtrlVal_12(DAT_00414180,0x2b,&local_24);
        _GetCtrlVal_12(DAT_0041418c,9,&local_20);
        _GetCtrlVal_12(DAT_00414180,0x1c,&local_1c);
        if (_DAT_00436748 == local_24) {
          local_24 = _DAT_00436768;
        }
        if (_DAT_00436748 <= local_1c) {
          _SetCtrlVal(DAT_0041417c,6,(double)(local_1c / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,6,(double)local_1c);
        }
        if (_DAT_00436748 <= local_20) {
          _SetCtrlVal(DAT_0041417c,7,(double)(local_20 / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,7,(double)local_20);
        }
        break;
      case 0x401:
        _atof();
        _SetCtrlVal();
        _GetCtrlVal_12(DAT_00414180,0x2b,&local_24);
        _GetCtrlVal_12(DAT_0041418c,9,&local_20);
        _GetCtrlVal_12(DAT_00414180,0x1c,&local_1c);
        if (_DAT_00436748 == local_24) {
          local_24 = _DAT_00436768;
        }
        if (_DAT_00436748 <= local_1c) {
          _SetCtrlVal(DAT_0041417c,6,(double)(local_1c / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,6,(double)local_1c);
        }
        if (_DAT_00436748 <= local_20) {
          _SetCtrlVal(DAT_0041417c,7,(double)(local_20 / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,7,(double)local_20);
        }
        break;
      case 0x404:
        fVar5 = (float10)_atof();
        _ecu_stb_decode((float)fVar5);
        _initial_secrets_fill_ecu = 0;
        break;
      case 0x405:
        fVar5 = (float10)_atof();
        _ecu_stbh_decode((float)fVar5);
        break;
      case 0x406:
        fVar5 = (float10)_atof();
        _ecu_xtal_temp_decode((float)fVar5);
        break;
      case 0x407:
        fVar5 = (float10)_atof();
        _ecu_hum_decode((float)fVar5);
        break;
      case 0x408:
        _atof();
        _SetCtrlVal();
        break;
      case 0x409:
        _ecu_optout = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414188,0xb,_ecu_optout);
        if (_ecu_optout == 1) {
          _hide_ecu_controls();
        }
        else {
          _show_ecu_controls();
        }
        break;
      case 0x40a:
        _decode_cop();
        _SetCtrlVal(DAT_00414194,4,&_sbuf_cop);
        break;
      case 0x40b:
        _decode_emp();
        _SetCtrlVal(DAT_00414194,7,&_sbuf_emp);
        break;
      case 0x40c:
        _decode_tdg();
        _SetCtrlVal(DAT_00414194,5,&_sbuf_tdg);
        break;
      case 0x40d:
        _decode_ecu();
        _SetCtrlVal(DAT_00414194,3,&_sbuf_ecu);
        break;
      case 0x40e:
        _decode_asc();
        _SetCtrlVal(DAT_00414194,6,&_sbuf_asc);
        break;
      case 0x40f:
        _sscanf(&_sbuf,&DAT_00436b80);
        _decode_tdg_stbh(local_10);
        break;
      case 0x410:
        _atof();
        _SetCtrlVal();
        break;
      case 0x411:
        _atof();
        _SetCtrlVal();
        break;
      case 0x412:
        _atof();
        _SetCtrlVal();
        break;
      case 0x413:
        _atof();
        _SetCtrlVal();
        break;
      case 0x415:
        _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
        _strstr(&_sbuf,&DAT_00436bf4);
        _SetCtrlVal(DAT_00414180,6);
        _strstr(&_sbuf,s____NENA_00436c3d + 3);
        _SetCtrlVal(DAT_00414180,8);
        fVar5 = _decodenum(0x414fa0);
        _SetCtrlVal(DAT_0041417c,0x2b,(double)fVar5);
        pcVar4 = _strstr(&_sbuf,&DAT_00436c98);
        _SetCtrlVal(DAT_0041417c,0x17,pcVar4 == (char *)0x0);
        break;
      case 0x416:
        _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
        _strstr(&_sbuf,&DAT_00436be4);
        _SetCtrlVal(DAT_00414180,9);
        _strstr(&_sbuf,s_RRANENA_00436c2d + 3);
        _SetCtrlVal(DAT_00414180,10);
        fVar5 = _decodenum(0x414fa0);
        _SetCtrlVal(DAT_0041417c,0x2a,(double)fVar5);
        pcVar4 = _strstr(&_sbuf,&DAT_00436c8c);
        _SetCtrlVal(DAT_0041417c,0x15,pcVar4 == (char *)0x0);
        break;
      case 0x417:
        _strstr(&_sbuf,&DAT_00436bdc);
        _SetCtrlVal(DAT_00414180,0xd);
        _strstr(&_sbuf,&DAT_00436c28);
        _SetCtrlVal(DAT_00414180,0xe);
        _strstr(&_sbuf,&DAT_00436c88);
        _SetCtrlVal(DAT_00414180,0x19);
        _decodenum(0x414fa0);
        _SetCtrlVal();
        break;
      case 0x418:
        _strstr(&_sbuf,&DAT_00436bd4);
        _SetCtrlVal(DAT_00414180,0xf);
        _strstr(&_sbuf,&DAT_00436c20);
        _SetCtrlVal(DAT_00414180,0x10);
        _strstr(&_sbuf,&DAT_00436c84);
        _SetCtrlVal(DAT_00414180,0x17);
        _decodenum(0x414fa0);
        _SetCtrlVal();
        break;
      case 0x419:
        _strstr(&_sbuf,&DAT_00436bcc);
        _SetCtrlVal(DAT_00414180,0xb);
        _strstr(&_sbuf,&DAT_00436c18);
        _SetCtrlVal(DAT_00414180,0xc);
        _strstr(&_sbuf,&DAT_00436c80);
        _SetCtrlVal(DAT_0041417c,0x14);
        _decodenum(0x414fa0);
        _SetCtrlVal();
        break;
      case 0x41a:
        pcVar4 = _strstr(&_sbuf,&DAT_00436e20);
        _SetCtrlVal(DAT_00414180,2,pcVar4 == (char *)0x0);
        break;
      case 0x41b:
        _strstr(&_sbuf,&DAT_00436e14);
        _SetCtrlVal(DAT_00414180,3);
        _strstr(&_sbuf,&DAT_00436e10);
        _SetCtrlAttribute();
        _strstr(&_sbuf,&DAT_00436e0c);
        _SetCtrlAttribute();
        _strstr(&_sbuf,&DAT_00436e08);
        _SetCtrlAttribute();
        _strstr(&_sbuf,&DAT_00436e04);
        _SetCtrlAttribute();
        pcVar4 = _strstr(&_sbuf,&DAT_00436e00);
        _SetCtrlVal(DAT_00414180,3,pcVar4 == (char *)0x0);
        break;
      case 0x41c:
        _decodenum_del(0x414fa0);
        _SetCtrlVal();
        break;
      case 0x41d:
        _atof();
        _SetCtrlVal();
        _GetCtrlVal_12(DAT_00414180,0x2b,&local_24);
        _GetCtrlVal_12(DAT_0041418c,9,&local_20);
        _GetCtrlVal_12(DAT_00414180,0x1c,&local_1c);
        _SetCtrlVal(DAT_0041417c,8,(double)local_1c);
        if (_DAT_00436748 == local_24) {
          local_24 = _DAT_00436768;
        }
        if (_DAT_00436748 <= local_1c) {
          _SetCtrlVal(DAT_0041417c,6,(double)(local_1c / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,6,(double)local_1c);
        }
        if (_DAT_00436748 <= local_20) {
          _SetCtrlVal(DAT_0041417c,7,(double)(local_20 / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,7,(double)local_20);
        }
        break;
      case 0x41e:
        _strstr(&_sbuf,&DAT_00436b74);
        _SetCtrlVal(DAT_00414180,0x27);
        pcVar4 = _strstr(&_sbuf,&DAT_00436ca4);
        _SetCtrlVal(DAT_00414180,0x25,pcVar4 == (char *)0x0);
        break;
      case 0x41f:
        _atof();
        _SetCtrlVal();
        break;
      case 0x420:
        _atof();
        _SetCtrlVal();
        break;
      case 0x421:
        fVar5 = (float10)_atof();
        _ecu_stbh_decode_ini((float)fVar5);
        break;
      case 0x422:
        _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
        _strstr(&_sbuf,&DAT_00436bfc);
        _SetCtrlVal(DAT_00414180,6);
        _strstr(&_sbuf,&DAT_00436c48);
        _SetCtrlVal(DAT_00414180,8);
        fVar5 = _decodenum(0x414fa0);
        _SetCtrlVal(DAT_0041417c,0x2b,(double)fVar5);
        pcVar4 = _strstr(&_sbuf,&DAT_00436ca0);
        _SetCtrlVal(DAT_0041417c,0x17,pcVar4 == (char *)0x0);
        break;
      case 0x423:
        _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
        _strstr(&_sbuf,&DAT_00436bec);
        _SetCtrlVal(DAT_00414180,9);
        _strstr(&_sbuf,s_VERNENA_00436c35 + 3);
        _SetCtrlVal(DAT_00414180,10);
        fVar5 = _decodenum(0x414fa0);
        _SetCtrlVal(DAT_0041417c,0x2a,(double)fVar5);
        pcVar4 = _strstr(&_sbuf,&DAT_00436c94);
        _SetCtrlVal(DAT_0041417c,0x15,pcVar4 == (char *)0x0);
        break;
      case 0x424:
        _atof();
        _SetCtrlVal();
        break;
      case 0x425:
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414180,0x22,iVar2);
        break;
      case 0x426:
        _GetCtrlVal_12(DAT_00414180,0x2b,&local_24);
        _GetCtrlVal_12(DAT_0041418c,9,&local_20);
        _GetCtrlVal_12(DAT_00414180,0x1c,&local_1c);
        if (_DAT_00436748 == local_24) {
          local_24 = _DAT_00436768;
        }
        if (_DAT_00436748 <= local_1c) {
          _SetCtrlVal(DAT_0041417c,6,(double)(local_1c / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,6,(double)local_1c);
        }
        if (_DAT_00436748 <= local_20) {
          _SetCtrlVal(DAT_0041417c,7,(double)(local_20 / local_24));
        }
        else {
          _SetCtrlVal(DAT_0041417c,7,(double)local_20);
        }
        break;
      case 0x427:
        pcVar4 = _strstr(&_sbuf,&DAT_00436c9c);
        _SetCtrlVal(DAT_0041417c,0x17,pcVar4 == (char *)0x0);
        break;
      case 0x428:
        pcVar4 = _strstr(&_sbuf,&DAT_00436c90);
        _SetCtrlVal(DAT_0041417c,0x15,pcVar4 == (char *)0x0);
        break;
      case 0x429:
        _atof();
        _SetCtrlVal();
        break;
      case 0x42a:
        _sscanf(&_sbuf,&DAT_00436b7c);
        _decode_tdg_stbh_nom(local_10);
        break;
      case 0x42b:
        _strstr(&_sbuf,&DAT_00436e1c);
        _SetCtrlVal(DAT_00414180,2);
        pcVar4 = _strstr(&_sbuf,&DAT_00436e18);
        if (pcVar4 == (char *)0x0) {
          _sprintf(&_g_par_str,s__n_INT_0043679a + 2);
          _push_inside_stack(0x7ee);
          _sprintf(&_g_par_str,s_VE_EXT_004367da + 2);
          _push_inside_stack(0x7ee);
        }
        break;
      case 0x42c:
        _emp_optout = _atoi(&_sbuf);
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414188,9,iVar2);
        if (_emp_optout == 1) {
          _hide_emp_controls();
        }
        else {
          _show_emp_controls();
        }
        break;
      case 0x42d:
        _hed_optout = _atoi(&_sbuf);
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414188,10,iVar2);
        break;
      case 0x42f:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        fVar5 = (float10)_atof();
        _SetCtrlAttribute(DAT_0041418c,2,0x2da,(double)fVar5);
        fVar5 = (float10)_atof();
        _SetCtrlAttribute(DAT_0041418c,8,0x2da,(double)fVar5);
        break;
      case 0x430:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        break;
      case 0x431:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        break;
      case 0x432:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        break;
      case 0x433:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        break;
      case 0x434:
        if (_initial_secrets_read != 0) {
          _atof();
          _SetCtrlVal();
        }
        _atof();
        _SetCtrlVal();
        _initial_secrets_read = 0;
        break;
      case 0x435:
        _atof();
        _SetCtrlVal();
        break;
      case 0x436:
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_0041419c,0x12,iVar2);
        break;
      case 0x438:
        pcVar4 = _strstr(&_sbuf,s_DCONT_00436d8b + 1);
        _SetCtrlVal(DAT_00414180,0x30,pcVar4 == (char *)0x0);
        break;
      case 0x43a:
        _verify = _verify + 1;
        break;
      case 0x43c:
        fVar5 = (float10)_atof();
        _ecu_tec_temp_decode((float)fVar5);
        break;
      case 0x43d:
        _pardon_first_time_user = 0;
        uVar3 = _atoi(&_sbuf);
        uVar1 = _atoi(&_sbuf);
        local_30 = (uint)((uVar3 & 1) != 0);
        _delay_monitor_status = local_30;
        if ((uVar1 & 2) != 0) {
          _SetCtrlVal(DAT_0041417c,0x17,0);
          _SetCtrlVal(DAT_0041417c,0x15,0);
          _call_for_reset_c1n2 = 1;
        }
        if (_curtain_not_open != 0) {
          _open_curtain();
          _curtain_not_open = 0;
        }
        break;
      case 0x43e:
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_0041417c,0x2f,iVar2);
        break;
      case 0x43f:
        iVar2 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414188,0xc,0 < iVar2);
        break;
      case 0x440:
        fVar5 = (float10)_atof();
        _ecu_stbh_decode_fault((float)fVar5);
        break;
      case 0x441:
        _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414190,0x14);
        _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414190,5);
        _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414190,9);
        uVar3 = _atoi(&_sbuf);
        _SetCtrlVal(DAT_00414190,4,(uVar3 & 8) != 0);
        break;
      default:
        if (1999 < local_c) {
          switch(local_c) {
          case 2000:
          case 0x7d1:
          case 0x7d2:
          case 0x7d3:
          case 0x7d4:
          case 0x7d5:
          case 0x7d6:
            break;
          default:
            if (local_c == 0x7f2) {
              _SetCtrlVal(DAT_0041417c,0x3a,&_sbuf);
            }
          }
        }
      }
    }
  }
  return;
}



/* ===== _hide_ecu_controls @ 0040ff51 ===== */

void _hide_ecu_controls(void)

{
  _SetCtrlAttribute(DAT_0041417c,0x10,0x212,0);
  _SetCtrlAttribute(DAT_00414188,0x10,0x212,0);
  _SetCtrlAttribute(DAT_00414188,0xf,0x212,0);
  _push_inside_stack(0x408);
  return;
}



/* ===== _hide_emp_controls @ 0040fef5 ===== */

void _hide_emp_controls(void)

{
  _SetCtrlAttribute(DAT_0041417c,0x13,0x212,0);
  return;
}



/* ===== _htons@4 @ 0041317e ===== */

void _htons_4(void)

{
                    /* WARNING: Could not recover jumptable at 0x0041317e. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_9();
  return;
}



/* ===== _humoverride @ 0040ecbe ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _humoverride(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,&DAT_00436dc4);
      _push_inside_stack(0x7ed);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 != local_8) {
        _push_inside_stack(0x421);
      }
    }
    else {
      _sprintf(&_g_par_str,&DAT_0043682c);
      _push_inside_stack(0x7ed);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 != local_8) {
        _push_inside_stack(0x421);
      }
    }
  }
  return 0;
}



/* ===== _init_global_parameters @ 00406758 ===== */

void _init_global_parameters(void)

{
  _strt_time2 = 0;
  _strt_time1 = 0;
  _SetCtrlAttribute(DAT_0041417c,0x2d,0x212,0);
  _SetAccessLevel(0);
  _com_par_loaded_ok = 0;
  _sprintf(&_SETTINGS_FILE,&DAT_004368a0,s_user_settings_txt_00436911 + 3);
  _last_fault_7 = 0;
  _last_fault_8 = 0;
  _last_fault_9 = 0;
  _corrupt_msg_cnt = 0;
  _g_message_balance_count = 0;
  _evnt_cmt = 0;
  _evnt_cmt_HV = 0;
  _keycnt = 0;
  _ATTEMPT_TURNON = 0;
  _initial_secrets_fill = 1;
  _initial_secrets_fill_mil = 1;
  _initial_secrets_fill_ecu = 1;
  _initial_secrets_fill_tdg = 1;
  _hum_blinkval = 0;
  _tem_blinkval = 0;
  _ecu_optout = 0;
  _hed_optout = 0;
  _emp_optout = 0;
  _LBO_STABILITY_STATE = 0;
  _call_for_reset_c1n2 = 0;
  _needs_initialization = 1;
  _old_on_ready = 0;
  _delay_monitor_status = 1;
  return;
}



/* ===== _ioctlsocket@12 @ 00413166 ===== */

void _ioctlsocket_12(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413166. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_12();
  return;
}



/* ===== _issue_event1 @ 004077dc ===== */

void _issue_event1(void)

{
  char *pcVar1;
  
  pcVar1 = (char *)_firstinline1();
  _WriteString(pcVar1);
  _g_message_balance_count = _g_message_balance_count + 1;
  return;
}



/* ===== _issue_event2 @ 0040781d ===== */

void _issue_event2(void)

{
  char *pcVar1;
  
  pcVar1 = (char *)_firstinline2();
  _WriteString(pcVar1);
  _g_message_balance_count = _g_message_balance_count + 1;
  return;
}



/* ===== _issue_fault_update_sequence @ 004130b7 ===== */

void _issue_fault_update_sequence(void)

{
  _push_inside_stack(0x441);
  _push_inside_stack(0x440);
  _push_inside_stack(0x3f6);
  _push_inside_stack(0x42a);
  _push_inside_stack(0x421);
  _push_inside_stack(0x441);
  _push_inside_stack(0x440);
  _push_inside_stack(0x3f6);
  _push_inside_stack(0x42a);
  _push_inside_stack(0x421);
  return;
}



/* ===== _issue_silent_event1 @ 00407807 ===== */

void _issue_silent_event1(void)

{
  char *pcVar1;
  
  pcVar1 = (char *)_firstinline1();
  _WriteString(pcVar1);
  return;
}



/* ===== _last_msg_authentic @ 004081c3 ===== */

int _last_msg_authentic(void)

{
  int local_c;
  int local_8;
  
  local_c = 0;
  for (local_8 = 0; local_8 < (int)(uint)DAT_00414450; local_8 = local_8 + 1) {
    local_c = local_c + (uint)(byte)(&_g_msg_process)[local_8];
  }
  return local_c;
}



/* ===== _main @ 00406e5b ===== */

undefined4 _main(void)

{
  int iVar1;
  undefined4 uVar2;
  
  _FAULTS_OPEN = 0;
  _SETUP_OPEN = 0;
  _SECRETS_OPEN = 0;
  _INFO_OPEN = 0;
  _HELP_OPEN = 0;
  _CCU_OPEN = 0;
  _DisableBreakOnLibraryErrors_0();
  iVar1 = _InitCVIRTEEx_12((HMODULE)0x0);
  if (iVar1 == 0) {
    uVar2 = 0xffffffff;
  }
  else {
    DAT_00414184 = _LoadPanel_12(0,s___Spitfire_uir_00436a61 + 3,7);
    if (DAT_00414184 < 0) {
      uVar2 = 0xffffffff;
    }
    else {
      DAT_00414180 = _LoadPanel_12(0,s_Spitfire_uir_00436a51 + 3,5);
      if (DAT_00414180 < 0) {
        uVar2 = 0xffffffff;
      }
      else {
        DAT_0041417c = _LoadPanel_12(0,s_Spitfire_uir_00436a41 + 3,6);
        if (DAT_0041417c < 0) {
          uVar2 = 0xffffffff;
        }
        else {
          DAT_0041418c = _LoadPanel_12(0,s_RFRSpitfire_uir_00436a31 + 3,9);
          if (DAT_0041418c < 0) {
            uVar2 = 0xffffffff;
          }
          else {
            DAT_00414190 = _LoadPanel_12(0,s__nQSpitfire_uir_00436a21 + 3,3);
            if (DAT_00414190 < 0) {
              uVar2 = 0xffffffff;
            }
            else {
              DAT_00414194 = _LoadPanel_12(0,s_rr_Spitfire_uir_00436a11 + 3,4);
              if (DAT_00414194 < 0) {
                uVar2 = 0xffffffff;
              }
              else {
                DAT_00414188 = _LoadPanel_12(0,s_T__Spitfire_uir_00436a01 + 3,2);
                if (DAT_00414188 < 0) {
                  uVar2 = 0xffffffff;
                }
                else {
                  DAT_0041419c = _LoadPanel_12(0,s_ER_Spitfire_uir_004369f1 + 3,8);
                  if (DAT_0041419c < 0) {
                    uVar2 = 0xffffffff;
                  }
                  else {
                    DAT_004141a0 = _LoadPanel_12(0,s_Spitfire_uir_004369e1 + 3,1);
                    if (DAT_004141a0 < 0) {
                      uVar2 = 0xffffffff;
                    }
                    else {
                      _SetCtrlAttribute(DAT_0041417c,0x31,0x262,0);
                      _SetCtrlAttribute(DAT_0041417c,0x36,0x262,0);
                      _InitServer(0x3e9);
                      _DisplayPanel_4(DAT_0041417c);
                      _LoadMenuBar_12(DAT_0041417c,s_erSpitfire_uir_004369d2 + 2,1);
                      uVar2 = _GetPanelMenuBar_4(DAT_0041417c);
                      _SetMenuBarAttribute(uVar2,0,500,1);
                      _init_global_parameters();
                      _openandconfigureport();
                      _strt_time2 = 0xb;
                      _strt_time1 = 0;
                      _SetSleepPolicy_4(1);
                      _CmtScheduleThreadPoolFunction_16(0xffffffff,&DAT_004068fa,0,0);
                      _CmtScheduleThreadPoolFunction_16(0xffffffff,&DAT_00406929,0,0);
                      _CmtScheduleThreadPoolFunction_16(0xffffffff,&LAB_00406953,0,0);
                      _RunUserInterface_0();
                      _CloseServer();
                      uVar2 = 0;
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
  return uVar2;
}



/* ===== _mil_stb_decode @ 00408a64 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _mil_stb_decode(float param_1)

{
  int iVar1;
  uint uVar2;
  undefined4 uVar3;
  undefined1 local_38;
  uint local_20;
  
  if (_hed_optout == 0) {
    if (param_1 < (float)_DAT_00436750) {
      local_20 = __ftol();
    }
    else {
      iVar1 = __ftol();
      local_20 = iVar1 + 0x80000000;
    }
    uVar2 = _MSB(local_20);
    if (param_1 < (float)_DAT_00436750) {
      uVar3 = __ftol();
      local_38 = (undefined1)uVar3;
    }
    else {
      uVar3 = __ftol();
      local_38 = (undefined1)uVar3;
    }
    _LSB(local_38);
    _comm_status_mil = uVar2 & 8;
    _SetCtrlVal(DAT_0041417c,0x11,_comm_status_mil == 0);
    if (_used_comm_status_mil != _comm_status_mil) {
      _push_initial_updates_mil();
      _used_comm_status_mil = _comm_status_mil;
    }
  }
  else {
    _comm_status_mil = 0;
    _SetCtrlVal(DAT_0041417c,0x11,0);
  }
  return;
}



/* ===== _open_curtain @ 0040b9a2 ===== */

void _open_curtain(void)

{
  undefined4 uVar1;
  
  uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
  _SetMenuBarAttribute(uVar1,0,500,0);
  _SetCtrlAttribute(DAT_0041417c,0x31,0x212,0);
  _SetCtrlAttribute(DAT_0041417c,0x36,0x212,0);
  return;
}



/* ===== _openandconfigureport @ 00406a03 ===== */

void _openandconfigureport(void)

{
  bool bVar1;
  int iVar2;
  int local_98;
  char local_94 [132];
  int local_10;
  uint local_c;
  int local_8;
  
  _sprintf(&_devicename,&DAT_0043689c,&DAT_00436cd8);
  _baudrate = 0x4b00;
  _parity = 0;
  _databits = 8;
  _stopbits = 1;
  _inputq = 0x200;
  _outputq = 0x200;
  _HOLD_THREAD = 1;
  while (iVar2 = _displaylen1(), 0 < iVar2) {
    _pop1();
  }
  while (iVar2 = _displaylen2(), 0 < iVar2) {
    _pop2();
  }
  bVar1 = false;
  _time((time_t *)&local_10);
  _time((time_t *)&local_c);
  while ((local_c < local_10 + 3U && (!bVar1))) {
    _time((time_t *)&local_c);
    local_98 = _Open_Udp_Port2(0x400);
    if (local_98 == 0) {
      bVar1 = true;
    }
    else {
      _Close_UDP_Port();
    }
  }
  if (local_98 == 0) {
    _sprintf(local_94,&DAT_00436898,s_Loading_data__please_wait_00436d91 + 3);
    _SetCtrlVal(DAT_0041417c,0x36,local_94);
    for (local_8 = 0; local_8 < 3; local_8 = local_8 + 1) {
      _push_inside_stack(1000);
      _issue_silent_event1();
      _pop1();
      _time((time_t *)&local_10);
      _time((time_t *)&local_c);
      _chars_read = 0;
      while ((local_c < local_10 + 3U && (_chars_read == 0))) {
        _time((time_t *)&local_c);
        _UDP_Refresh();
        _Try_Receive_UDP();
      }
      if ((local_8 == 2) && (0 < _chars_read)) {
        _g_message_balance_count = 0;
        _push_initial_updates();
        _refresh_connectivity();
      }
    }
    _HOLD_THREAD = 0;
  }
  else {
    _sprintf(local_94,s_Com_error___cannot_open__00436eb0);
    _SetCtrlVal(DAT_0041417c,0x36,local_94);
    _close_curtain();
  }
  return;
}



/* ===== _optoutcompressorcall @ 00411eca ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _optoutcompressorcall(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined4 local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414188,10,&local_c);
    _sprintf(&_g_par_str,&DAT_004368e0,local_c);
    _push_inside_stack(0x7f3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 == local_8) {
      _hed_optout = local_c;
    }
    else {
      _push_inside_stack(0x42d);
    }
  }
  return 0;
}



/* ===== _optoutecucall @ 0040e5f3 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _optoutecucall(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_00414188,0xb,&local_c);
    _sprintf(&_g_par_str,&DAT_004368ec,local_c);
    _push_inside_stack(0x7e8);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 == local_8) {
      _ecu_optout = local_c;
      if (local_c == 0) {
        _show_ecu_controls();
      }
      else {
        _hide_ecu_controls();
      }
    }
    else {
      _push_inside_stack(0x409);
    }
  }
  return 0;
}



/* ===== _osc_mode @ 0040e913 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _osc_mode(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_INT_00436794);
      _push_inside_stack(0x7ee);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 != local_8) {
        _push_inside_stack(0x41a);
      }
    }
    else {
      _sprintf(&_g_par_str,s_EXT_004367d4);
      _push_inside_stack(0x7ee);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 != local_8) {
        _push_inside_stack(0x41a);
      }
    }
  }
  return 0;
}



/* ===== _parse_command5 @ 0040ab3c ===== */

undefined4 __cdecl _parse_command5(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 3) {
    _sprintf(&_g_par_str,&DAT_00436b44);
    _push_inside_stack(0x7ec);
    _push_inside_stack(0x3f5);
    _SetCtrlVal(DAT_00414188,8,0);
  }
  return 0;
}



/* ===== _picture_Callback1 @ 004107b5 ===== */

undefined4 __cdecl _picture_Callback1(undefined4 param_1,undefined4 param_2,int param_3)

{
  if (param_3 == 3) {
    DAT_0043668c = 1;
    _sprintf(&_g_par_str,&DAT_00436b20);
    _push_inside_stack(0x7d9);
    _SetCtrlAttribute(DAT_0041417c,4,0x4f7,1);
  }
  else if (param_3 == 5) {
    DAT_0043668c = 2;
    _sprintf(&_g_par_str,&DAT_00436b1c);
    _push_inside_stack(0x7da);
    _SetCtrlAttribute(DAT_0041417c,4,0x4f7,1);
  }
  return 0;
}



/* ===== _picture_Callback2 @ 00410928 ===== */

undefined4 __cdecl _picture_Callback2(undefined4 param_1,undefined4 param_2,undefined4 param_3)

{
  switch(param_3) {
  case 3:
    _sprintf(&_g_par_str,&DAT_00436b14);
    _push_inside_stack(0x7dc);
    break;
  case 4:
    _sprintf(&_g_par_str,&DAT_00436b10);
    _push_inside_stack(0x7dc);
    break;
  case 5:
    _sprintf(&_g_par_str,&DAT_00436b0c);
    _push_inside_stack(0x7db);
    break;
  case 6:
    _sprintf(&_g_par_str,&DAT_00436b08);
    _push_inside_stack(0x7db);
  }
  return 0;
}



/* ===== _pop1 @ 0040772a ===== */

void _pop1(void)

{
  void *_Memory;
  undefined4 *_Memory_00;
  
  _Memory_00 = _fifo1;
  if (_fifo1 != (undefined4 *)0x0) {
    _Memory = (void *)*_fifo1;
    _fifo1 = (undefined4 *)_fifo1[1];
    _free(_Memory);
    _free(_Memory_00);
  }
  return;
}



/* ===== _pop2 @ 004074f3 ===== */

void _pop2(void)

{
  void *_Memory;
  undefined4 *_Memory_00;
  
  _Memory_00 = _fifo2;
  if (_fifo2 != (undefined4 *)0x0) {
    _Memory = (void *)*_fifo2;
    _fifo2 = (undefined4 *)_fifo2[1];
    _free(_Memory);
    _free(_Memory_00);
  }
  return;
}



/* ===== _push1 @ 004075a5 ===== */

void __cdecl _push1(int param_1)

{
  void *_Dst;
  void *pvVar1;
  int *local_c;
  int local_8;
  
  _Dst = _malloc(8);
  _memset(_Dst,0,8);
  if (_fifo1 == (int *)0x0) {
    _fifo1 = (int *)_malloc(8);
    local_c = _fifo1;
  }
  else {
    for (local_c = _fifo1; local_c[1] != 0; local_c = (int *)local_c[1]) {
    }
  }
  pvVar1 = _malloc(0x20);
  *local_c = (int)pvVar1;
  for (local_8 = 0; local_8 < 0x1e; local_8 = local_8 + 1) {
    *(undefined1 *)(*local_c + local_8) = *(undefined1 *)(local_8 + param_1);
  }
  local_c[1] = (int)_Dst;
  return;
}



/* ===== _push2 @ 0040736e ===== */

void __cdecl _push2(int param_1)

{
  void *_Dst;
  void *pvVar1;
  int *local_c;
  int local_8;
  
  _Dst = _malloc(8);
  _memset(_Dst,0,8);
  if (_fifo2 == (int *)0x0) {
    _fifo2 = (int *)_malloc(8);
    local_c = _fifo2;
  }
  else {
    for (local_c = _fifo2; local_c[1] != 0; local_c = (int *)local_c[1]) {
    }
  }
  pvVar1 = _malloc(0x20);
  *local_c = (int)pvVar1;
  for (local_8 = 0; local_8 < 0x1e; local_8 = local_8 + 1) {
    *(undefined1 *)(*local_c + local_8) = *(undefined1 *)(local_8 + param_1);
  }
  local_c[1] = (int)_Dst;
  return;
}



/* ===== _push_initial_updates @ 00407906 ===== */

void _push_initial_updates(void)

{
  _push_inside_stack(0x42d);
  _push_inside_stack(0x42c);
  _push_inside_stack(0x43f);
  _push_inside_stack(0x409);
  _push_inside_stack(0x40e);
  _push_initial_updates_ecu();
  _push_initial_updates_mil();
  _push_initial_updates_tdg();
  _push_initial_updates_emp();
  _push_inside_stack(0x426);
  return;
}



/* ===== _push_initial_updates_ecu @ 00407970 ===== */

void _push_initial_updates_ecu(void)

{
  _initial_secrets_fill_ecu = 1;
  _push_inside_stack(0x40d);
  _push_inside_stack(0x408);
  _push_inside_stack(0x421);
  return;
}



/* ===== _push_initial_updates_emp @ 00407ada ===== */

void _push_initial_updates_emp(void)

{
  _initial_secrets_fill = 1;
  _push_inside_stack(0x40b);
  _push_inside_stack(0x3f1);
  _push_inside_stack(0x3f2);
  _push_inside_stack(0x3f3);
  _push_inside_stack(0x3f4);
  _push_inside_stack(0x41d);
  _initial_secrets_fill_empower = 1;
  _initial_secrets_read = 1;
  _push_inside_stack(0x42f);
  _push_inside_stack(0x430);
  _push_inside_stack(0x431);
  _push_inside_stack(0x432);
  _push_inside_stack(0x433);
  _push_inside_stack(0x434);
  _sprintf(&_g_par_str,&DAT_00436830);
  _push_inside_stack(0x7ff);
  _push_inside_stack(0x436);
  return;
}



/* ===== _push_initial_updates_mil @ 004079ac ===== */

void _push_initial_updates_mil(void)

{
  _initial_secrets_fill_mil = 1;
  _push_inside_stack(0x40a);
  _push_inside_stack(0x424);
  return;
}



/* ===== _push_initial_updates_tdg @ 004079db ===== */

void _push_initial_updates_tdg(void)

{
  _initial_secrets_fill_tdg = 1;
  _push_inside_stack(0x43e);
  _push_inside_stack(0x40c);
  _push_inside_stack(0x415);
  _push_inside_stack(0x416);
  _push_inside_stack(0x417);
  _push_inside_stack(0x418);
  _push_inside_stack(0x419);
  _push_inside_stack(0x410);
  _push_inside_stack(0x411);
  _push_inside_stack(0x400);
  _push_inside_stack(0x401);
  _push_inside_stack(0x41c);
  _push_inside_stack(0x41d);
  _push_inside_stack(0x41e);
  _push_inside_stack(0x42b);
  _push_inside_stack(0x41b);
  _push_inside_stack(0x41d);
  _push_inside_stack(0x438);
  return;
}



/* ===== _push_inside_stack @ 00407e91 ===== */

void __cdecl _push_inside_stack(int param_1)

{
  _update_string(param_1);
  _push1(0x4141d4);
  return;
}



/* ===== _push_outside_stack @ 00407e6e ===== */

void __cdecl _push_outside_stack(int param_1)

{
  _update_string(param_1);
  _push2(0x4141d4);
  return;
}



/* ===== _push_usual_auto_updates @ 00407bd5 ===== */

void _push_usual_auto_updates(void)

{
  undefined1 local_18 [4];
  undefined1 local_14 [4];
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined4 local_8;
  
  _check_if_system_healthy();
  local_8 = _GetCtrlVal_12(DAT_0041417c,0x11,local_c);
  local_8 = _GetCtrlVal_12(DAT_0041417c,0xd,local_10);
  local_8 = _GetCtrlVal_12(DAT_0041417c,0x13,local_14);
  local_8 = _GetCtrlVal_12(DAT_0041417c,0x10,local_18);
  if (_call_for_reset_c1n2 != 0) {
    _push_outside_stack(0x806);
    _call_for_reset_c1n2 = 0;
  }
  if (0 < _gAccessLevel) {
    _push_outside_stack(0x40f);
    _push_outside_stack(0x420);
    _push_outside_stack(0x40f);
    _push_outside_stack(0x41f);
    _push_outside_stack(0x40f);
    _push_outside_stack(0x412);
    _push_outside_stack(0x40f);
    _push_outside_stack(0x413);
  }
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3f7);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3fb);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3f5);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x404);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3ef);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3f0);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x405);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x406);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x429);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x407);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x3fd);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x435);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x43c);
  _push_outside_stack(0x40f);
  _push_outside_stack(0x43d);
  _push_outside_stack(0x40f);
  return;
}



/* ===== _reconnect @ 00406e31 ===== */

void _reconnect(void)

{
  if (_pardon_first_time_user == 0) {
    _waitforuser_holdthread();
  }
  _Close_UDP_Port();
  _openandconfigureport();
  return;
}



/* ===== _recvfrom@24 @ 0041314e ===== */

void _recvfrom_24(void)

{
                    /* WARNING: Could not recover jumptable at 0x0041314e. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_17();
  return;
}



/* ===== _refresh_connectivity @ 0040e46d ===== */

time_t _refresh_connectivity(void)

{
  time_t tVar1;
  
  tVar1 = _time((time_t *)&_strt_time1);
  return tVar1;
}



/* ===== _secretcall1 @ 00412037 ===== */

undefined4 __cdecl _secretcall1(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d34,(double)local_8);
    _push_inside_stack(0x7f5);
    _sprintf(&_g_par_str,&DAT_00436ae0);
    _push_inside_stack(0x7fd);
  }
  return 0;
}



/* ===== _secretcall2 @ 004120bc ===== */

undefined4 __cdecl _secretcall2(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d2c,(double)local_8);
    _push_inside_stack(0x7f6);
    _sprintf(&_g_par_str,&DAT_00436adc);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x42f);
  }
  return 0;
}



/* ===== _secretcall3 @ 0041214e ===== */

undefined4 __cdecl _secretcall3(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d24,(double)local_8);
    _push_inside_stack(0x7f7);
    _sprintf(&_g_par_str,&DAT_00436ad8);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x430);
  }
  return 0;
}



/* ===== _secretcall4 @ 004121e0 ===== */

undefined4 __cdecl _secretcall4(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d1c,(double)local_8);
    _push_inside_stack(0x7f8);
    _sprintf(&_g_par_str,&DAT_00436ad4);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x431);
  }
  return 0;
}



/* ===== _secretcall5 @ 00412272 ===== */

undefined4 __cdecl _secretcall5(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d14,(double)local_8);
    _push_inside_stack(0x7f9);
    _sprintf(&_g_par_str,&DAT_00436ad0);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x432);
  }
  return 0;
}



/* ===== _secretcall6 @ 00412304 ===== */

undefined4 __cdecl _secretcall6(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d0c,(double)local_8);
    _push_inside_stack(0x7fa);
    _sprintf(&_g_par_str,&DAT_00436acc);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x433);
  }
  return 0;
}



/* ===== _secretcall7 @ 00412396 ===== */

undefined4 __cdecl _secretcall7(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d04,(double)local_8);
    _push_inside_stack(0x7fb);
    _sprintf(&_g_par_str,&DAT_00436ac8);
    _push_inside_stack(0x7fd);
    _push_inside_stack(0x434);
  }
  return 0;
}



/* ===== _sendto@24 @ 00413184 ===== */

void _sendto_24(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413184. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_20();
  return;
}



/* ===== _server_DisplayPanel @ 00406112 ===== */

void _server_DisplayPanel(void)

{
  _DisplayPanel_4(DAT_00434d60);
  return;
}



/* ===== _server_HidePanel @ 00406126 ===== */

void _server_HidePanel(void)

{
  _HidePanel_4(DAT_00434d60);
  return;
}



/* ===== _set_max_current @ 0040aaee ===== */

undefined4 _set_max_current(void)

{
  return 0;
}



/* ===== _setbwd1 @ 0040f5ea ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setbwd1(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_1_NBWD_00436e30);
    }
    else {
      _sprintf(&_g_par_str,s_1_BWD_00436ce0);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x415);
    }
  }
  return 0;
}



/* ===== _setbwd2 @ 0040f6bc ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setbwd2(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_2_NBWD_00436980);
    }
    else {
      _sprintf(&_g_par_str,s_2_BWD_0043683c);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x416);
    }
  }
  return 0;
}



/* ===== _setbwd3 @ 0040f932 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setbwd3(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_3_NBWD_00436aac);
    }
    else {
      _sprintf(&_g_par_str,s_3_BWD_004368e4);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x417);
    }
  }
  return 0;
}



/* ===== _setbwd4 @ 0040fa04 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setbwd4(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_4_NBWD_00436ea0);
    }
    else {
      _sprintf(&_g_par_str,s_4_BWD_00436e38);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x418);
    }
  }
  return 0;
}



/* ===== _setbwd5 @ 0040fad6 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setbwd5(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_5_NBWD_00436988);
    }
    else {
      _sprintf(&_g_par_str,s_5_BWD_00436870);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x419);
    }
  }
  return 0;
}



/* ===== _setena1 @ 0040f860 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setena1(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s__T_1_NENA_00436f1a + 2);
    }
    else {
      _sprintf(&_g_par_str,s_1_ENA_00436e74);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x415);
    }
  }
  return 0;
}



/* ===== _setena2 @ 0040f78e ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setena2(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_de_2_NENA_00436cce + 2);
    }
    else {
      _sprintf(&_g_par_str,s_2_ENA_00436c78);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x416);
    }
  }
  return 0;
}



/* ===== _setena3 @ 0040fba8 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setena3(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_3_NENA_00436ea8);
    }
    else {
      _sprintf(&_g_par_str,s_3_ENA_00436df8);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x417);
    }
  }
  return 0;
}



/* ===== _setena4 @ 0040fc7a ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setena4(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_4_NENA_00436978);
    }
    else {
      _sprintf(&_g_par_str,s_4_ENA_00436834);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x418);
    }
  }
  return 0;
}



/* ===== _setena5 @ 0040fd4c ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _setena5(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_S_5_NENA_00436e7b + 1);
    }
    else {
      _sprintf(&_g_par_str,s_OD_5_ENA_00436dae + 2);
    }
    _push_inside_stack(0x7e3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 != local_8) {
      _push_inside_stack(0x419);
    }
  }
  return 0;
}



/* ===== _setopmode @ 00412584 ===== */

undefined4 __cdecl _setopmode(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_c;
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s_def_CONT_00436f55 + 3);
    }
    if (local_8 == 1) {
      _sprintf(&_g_par_str,s_COUNT_004367f4);
    }
    if (local_8 == 2) {
      _sprintf(&_g_par_str,s_V_COUNT_1_00436907 + 1);
    }
    _push_inside_stack(0x800);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (local_c == 0) {
      if (local_8 == 2) {
        _SetCtrlVal(param_1,param_2,1);
      }
    }
    else {
      _push_inside_stack(0x438);
    }
  }
  return 0;
}



/* ===== _setsockopt@20 @ 00413154 ===== */

void _setsockopt_20(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413154. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_21();
  return;
}



/* ===== _show_ccu @ 0040734d ===== */

void _show_ccu(void)

{
  _CCU_OPEN = 1;
  _DisplayPanel_4(DAT_00414188);
  return;
}



/* ===== _show_ecu_controls @ 0040ffd2 ===== */

void _show_ecu_controls(void)

{
  _SetCtrlAttribute(DAT_0041417c,0x10,0x212,1);
  _SetCtrlAttribute(DAT_00414188,0x10,0x212,1);
  _SetCtrlAttribute(DAT_00414188,0xf,0x212,1);
  _push_inside_stack(0x408);
  return;
}



/* ===== _show_emp_controls @ 0040ff23 ===== */

void _show_emp_controls(void)

{
  _SetCtrlAttribute(DAT_0041417c,0x13,0x212,1);
  return;
}



/* ===== _show_faults @ 004072ea ===== */

void _show_faults(void)

{
  _FAULTS_OPEN = 1;
  _DisplayPanel_4(DAT_00414190);
  return;
}



/* ===== _show_help @ 0040732c ===== */

void _show_help(void)

{
  _HELP_OPEN = 1;
  _DisplayPanel_4(DAT_00414194);
  return;
}



/* ===== _show_info @ 0040730b ===== */

void _show_info(void)

{
  _INFO_OPEN = 1;
  _DisplayPanel_4(DAT_00414180);
  return;
}



/* ===== _show_secrets @ 004072a8 ===== */

void _show_secrets(void)

{
  _SECRETS_OPEN = 1;
  _DisplayPanel_4(DAT_00414184);
  return;
}



/* ===== _show_setup @ 004072c9 ===== */

void _show_setup(void)

{
  _SETUP_OPEN = 1;
  _DisplayPanel_4(DAT_0041418c);
  return;
}



/* ===== _slideqswprf @ 0040acda ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _slideqswprf(undefined4 param_1,undefined4 param_2,int param_3)

{
  float fStack_18;
  float fStack_14;
  float fStack_10;
  float fStack_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_0041418c,9,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d84,(double)(local_8 / _DAT_00436770));
    _push_inside_stack(0x7d4);
    _GetCtrlVal_12(DAT_0041417c,0x30,&fStack_c);
    if (_DAT_00436748 == fStack_c) {
      _GetCtrlVal_12(DAT_0041418c,9,&local_8);
      _SetCtrlVal(DAT_0041417c,9,(double)local_8);
      _GetCtrlVal_12(DAT_00414180,0x2b,&fStack_18);
      _GetCtrlVal_12(DAT_0041418c,9,&fStack_14);
      _GetCtrlVal_12(DAT_00414180,0x1c,&fStack_10);
      if (_DAT_00436748 == fStack_18) {
        fStack_18 = _DAT_00436768;
      }
      if (_DAT_00436748 <= fStack_10) {
        _SetCtrlVal(DAT_0041417c,6,(double)(fStack_10 / fStack_18));
      }
      else {
        _SetCtrlVal(DAT_0041417c,6,(double)fStack_10);
      }
      if (_DAT_00436748 <= fStack_14) {
        _SetCtrlVal(DAT_0041417c,7,(double)(fStack_14 / fStack_18));
      }
      else {
        _SetCtrlVal(DAT_0041417c,7,(double)fStack_14);
      }
    }
    else {
      _push_inside_stack(0x3f2);
    }
  }
  return 0;
}



/* ===== _slideqswpw @ 0040aecd ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _slideqswpw(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_0041418c,10,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d7c,(double)local_8);
    _push_inside_stack(0x7d7);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (_DAT_00436748 != local_c) {
      _push_inside_stack(0x3f3);
    }
  }
  return 0;
}



/* ===== _slideqswsrc @ 0040af6e ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _slideqswsrc(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_0041418c,0xb,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d74,(double)local_8);
    _push_inside_stack(0x7d8);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (_DAT_00436748 != local_c) {
      _push_inside_stack(0x3f4);
    }
  }
  return 0;
}



/* ===== _slidesetcurr @ 0040b00f ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _slidesetcurr(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(DAT_0041418c,8,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d6c,(double)(local_8 * _DAT_00436770));
    _push_inside_stack(0x7d3);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_c);
    if (_DAT_00436748 != local_c) {
      _push_inside_stack(0x3f1);
    }
  }
  return 0;
}



/* ===== _socket@12 @ 00413178 ===== */

void _socket_12(void)

{
                    /* WARNING: Could not recover jumptable at 0x00413178. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Ordinal_23();
  return;
}



/* ===== _spc_strcpy @ 004066e8 ===== */

void __cdecl _spc_strcpy(int param_1,int param_2)

{
  undefined4 local_8;
  
  for (local_8 = 0; (*(char *)(local_8 + param_2) != '\0' && (*(char *)(local_8 + param_2) != '\r'))
      ; local_8 = local_8 + 1) {
    *(undefined1 *)(param_1 + local_8) = *(undefined1 *)(local_8 + param_2);
  }
  *(undefined1 *)(local_8 + param_1) = 0;
  return;
}



/* ===== _strnsendcllback @ 00410a10 ===== */

undefined4 _strnsendcllback(void)

{
  undefined1 local_cc [200];
  
  _GetCtrlVal_12(DAT_0041417c,0x3b,local_cc);
  _sprintf(&_g_par_str,&DAT_00436880,local_cc);
  _push_inside_stack(0x7f2);
  return 0;
}



/* ===== _swChannelEnableCallback_btn1 @ 0040f109 ===== */

undefined4 __cdecl _swChannelEnableCallback_btn1(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s__d_off_00436b6c,1);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    }
    else {
      _sprintf(&_g_par_str,s__d_on_0043696f + 1,1);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    }
  }
  return 0;
}



/* ===== _swChannelEnableCallback_btn2 @ 0040f1e0 ===== */

undefined4 __cdecl _swChannelEnableCallback_btn2(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s__d_off_00436b64,2);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    }
    else {
      _sprintf(&_g_par_str,s__d_on_00436967 + 1,2);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    }
  }
  return 0;
}



/* ===== _swChannelEnableCallback_btn3 @ 0040f2b7 ===== */

undefined4 __cdecl _swChannelEnableCallback_btn3(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s__d_off_00436b5c,3);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x417);
      }
    }
    else {
      _sprintf(&_g_par_str,s____d_on_0043695f + 1,3);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x417);
      }
    }
  }
  return 0;
}



/* ===== _swChannelEnableCallback_btn4 @ 0040f3c8 ===== */

undefined4 __cdecl _swChannelEnableCallback_btn4(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s__d_off_00436b54,4);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x418);
      }
    }
    else {
      _sprintf(&_g_par_str,s__d_on_00436957 + 1,4);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x418);
      }
    }
  }
  return 0;
}



/* ===== _swChannelEnableCallback_btn5 @ 0040f4d9 ===== */

undefined4 __cdecl _swChannelEnableCallback_btn5(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (local_8 == 0) {
      _sprintf(&_g_par_str,s__d_off_00436b49 + 3,5);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x419);
      }
    }
    else {
      _sprintf(&_g_par_str,s__d_on_00436950,5);
      _push_inside_stack(0x7e3);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (local_8 != 0) {
        _push_inside_stack(0x419);
      }
    }
  }
  return 0;
}



/* ===== _tdg_fault_override @ 0041305a ===== */

undefined4 __cdecl _tdg_fault_override(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined4 local_8;
  
  _GetCtrlVal_12(param_1,param_2,&local_8);
  if (param_3 == 1) {
    _sprintf(&_g_par_str,&DAT_004367ec,local_8);
    _push_inside_stack(0x805);
  }
  return 0;
}



/* ===== _tdg_stb_decode @ 00408905 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __cdecl _tdg_stb_decode(float param_1)

{
  int iVar1;
  uint uVar2;
  undefined4 uVar3;
  undefined1 local_38;
  uint local_20;
  
  if (param_1 < (float)_DAT_00436750) {
    local_20 = __ftol();
  }
  else {
    iVar1 = __ftol();
    local_20 = iVar1 + 0x80000000;
  }
  uVar2 = _MSB(local_20);
  if (param_1 < (float)_DAT_00436750) {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  else {
    uVar3 = __ftol();
    local_38 = (undefined1)uVar3;
  }
  _LSB(local_38);
  _comm_status_tdg = uVar2 & 8;
  _SetCtrlVal(DAT_0041417c,0xd,_comm_status_tdg == 0);
  if (_used_comm_status_tdg != _comm_status_tdg) {
    _push_initial_updates_tdg();
    _used_comm_status_tdg = _comm_status_tdg;
  }
  return;
}



/* ===== _teconoff @ 00410720 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _teconoff(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,&DAT_00436b24);
      _push_inside_stack(0x7e7);
    }
    else {
      _sprintf(&_g_par_str,&DAT_00436b28);
      _push_inside_stack(0x7e6);
    }
  }
  return 0;
}



/* ===== _tmr_Data_Logger @ 00412e60 ===== */

undefined4 __cdecl _tmr_Data_Logger(undefined4 param_1,undefined4 param_2,int param_3)

{
  int local_14;
  FILE *local_10;
  float local_c;
  float local_8;
  
  if ((param_3 == 0xf) && (_GetCtrlVal_12(DAT_004141a0,3,&local_14), local_14 != 0)) {
    _GetCtrlVal_12(DAT_0041418c,2,&local_c);
    _GetCtrlVal_12(DAT_0041419c,0xf,&local_8);
    local_10 = _fopen(s_datalog_csv_00436e89 + 3,&DAT_00436f4c);
    if (local_10 != (FILE *)0x0) {
      _fprintf(local_10,s_____2f____2f_004367c6 + 2,(double)local_c,(double)local_8);
      _fclose(local_10);
    }
  }
  return 0;
}



/* ===== _tmr_Mouse_Callback1 @ 00410885 ===== */

undefined4 __cdecl _tmr_Mouse_Callback1(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined1 local_18 [4];
  int local_14;
  int local_10;
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  if (((param_3 == 0xf) &&
      (_GetGlobalMouseState_24(0,local_8,local_c,&local_10,&local_14,local_18), local_10 == 0)) &&
     (local_14 == 0)) {
    _sprintf(&_g_par_str,&DAT_00436b18);
    _push_inside_stack(0x7dd);
    _SetCtrlAttribute(DAT_0041417c,4,0x4f7,0);
  }
  return 0;
}



/* ===== _trig_mode @ 0040ea14 ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _trig_mode(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    if (_DAT_00436748 == local_8) {
      _sprintf(&_g_par_str,s_1_INT_00436f4f + 1);
      _push_inside_stack(0x7ef);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 == local_8) {
        _SetCtrlAttribute(DAT_0041417c,6,0x212,1);
        _SetCtrlAttribute(DAT_0041417c,7,0x212,0);
        _SetCtrlAttribute(DAT_0041417c,8,0x212,1);
        _SetCtrlAttribute(DAT_0041417c,9,0x212,0);
      }
      else {
        _push_inside_stack(0x41b);
      }
    }
    else {
      _sprintf(&_g_par_str,&DAT_00436e84);
      _push_inside_stack(0x7ef);
      _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
      if (_DAT_00436748 == local_8) {
        _SetCtrlAttribute(DAT_0041417c,6,0x212,0);
        _SetCtrlAttribute(DAT_0041417c,7,0x212,1);
        _SetCtrlAttribute(DAT_0041417c,8,0x212,0);
        _SetCtrlAttribute(DAT_0041417c,9,0x212,1);
      }
      else {
        _push_inside_stack(0x41b);
      }
    }
  }
  return 0;
}



/* ===== _trig_reprate @ 0040edbf ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 __cdecl _trig_reprate(undefined4 param_1,undefined4 param_2,int param_3)

{
  float local_14;
  float local_10;
  float local_c;
  float local_8;
  
  if (param_3 == 1) {
    _GetCtrlVal_12(param_1,param_2,&local_8);
    _sprintf(&_g_par_str,s__5_2f_00436d4c,(double)local_8);
    _push_inside_stack(0x7f0);
    _GetCtrlVal_12(DAT_0041417c,0x30,&local_8);
    if (_DAT_00436748 == local_8) {
      _GetCtrlVal_12(DAT_00414180,0x2b,&local_14);
      _GetCtrlVal_12(DAT_0041418c,9,&local_10);
      _GetCtrlVal_12(DAT_00414180,0x1c,&local_c);
      _SetCtrlVal(DAT_0041417c,8,(double)local_c);
      if (_DAT_00436748 == local_14) {
        local_14 = _DAT_00436768;
      }
      if (_DAT_00436748 <= local_c) {
        _SetCtrlVal(DAT_0041417c,6,(double)(local_c / local_14));
      }
      else {
        _SetCtrlVal(DAT_0041417c,6,(double)local_c);
      }
      if (_DAT_00436748 <= local_10) {
        _SetCtrlVal(DAT_0041417c,7,(double)(local_10 / local_14));
      }
      else {
        _SetCtrlVal(DAT_0041417c,7,(double)local_10);
      }
    }
    else {
      _push_inside_stack(0x41d);
    }
  }
  return 0;
}



/* ===== _update_string @ 00407eb4 ===== */

void __cdecl _update_string(int param_1)

{
  undefined *puVar1;
  
  puVar1 = _get_tag_title(param_1);
  _sprintf(&_fin_msg,s___d__s_004367e4,param_1,puVar1);
  if (1999 < param_1) {
    _strcat(&_fin_msg,&_g_par_str);
  }
  if (param_1 == 0x402) {
    _strcat(&_fin_msg,&_g_par_str);
  }
  return;
}



/* ===== _validate_tec_temp @ 0040886d ===== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

bool __cdecl _validate_tec_temp(float param_1)

{
  if (10 < DAT_004366b4) {
    DAT_004366b4 = 10;
  }
  if (param_1 <= _DAT_00436758) {
    DAT_004366b4 = 0;
  }
  else {
    DAT_004366b4 = DAT_004366b4 + 1;
  }
  return 4 < DAT_004366b4;
}



/* ===== _waitforuser_holdthread @ 00406dce ===== */

void _waitforuser_holdthread(void)

{
  undefined4 uVar1;
  
  _DisplayPanel_4(DAT_0041417c);
  uVar1 = _GetPanelMenuBar_4(DAT_0041417c);
  _SetMenuBarAttribute(uVar1,0,500,1);
  _HOLD_THREAD = 1;
  _MessagePopup_8(s_3Warning_00436ce7 + 1,s_iRemote_system_not_responding__c_00436dc7 + 1);
  return;
}


