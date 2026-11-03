$ErrorActionPreference='Stop'
Add-Type @'
using System;using System.Net.Sockets;using System.Text;using System.Security.Cryptography;using System.Threading;
public static class LocalVmConsole {
 static byte[] Read(NetworkStream s,int n){byte[] b=new byte[n];int p=0;while(p<n){int k=s.Read(b,p,n-p);if(k<=0)throw new Exception("console EOF");p+=k;}return b;}
 static uint U32(byte[] b,int p){return ((uint)b[p]<<24)|((uint)b[p+1]<<16)|((uint)b[p+2]<<8)|b[p+3];}
 static void Key(NetworkStream s,uint k,bool down){byte[] b={4,(byte)(down?1:0),0,0,(byte)(k>>24),(byte)(k>>16),(byte)(k>>8),(byte)k};s.Write(b,0,b.Length);}
 static void Tap(NetworkStream s,uint k){Key(s,k,true);Thread.Sleep(90);Key(s,k,false);Thread.Sleep(60);}
 public static void Run(string password){
 using(var c=new TcpClient()){c.Connect("127.0.0.1",5905);var s=c.GetStream();s.ReadTimeout=4000;s.WriteTimeout=4000;
 string version=Encoding.ASCII.GetString(Read(s,12));if(!version.StartsWith("RFB 003."))throw new Exception("Unexpected RFB greeting");
 byte[] protocol=Encoding.ASCII.GetBytes("RFB 003.008\n");s.Write(protocol,0,12);int n=Read(s,1)[0];if(n==0)throw new Exception("Console security negotiation failed");byte[] sec=Read(s,n);if(Array.IndexOf(sec,(byte)2)<0)throw new Exception("Password-authenticated console required");
 s.WriteByte(2);byte[] challenge=Read(s,16),key=new byte[8];byte[] pw=Encoding.ASCII.GetBytes(password);
 for(int i=0;i<8;i++){byte v=i<pw.Length?pw[i]:(byte)0,r=0;for(int j=0;j<8;j++){r=(byte)((r<<1)|(v&1));v>>=1;}key[i]=r;}
 using(var des=DES.Create()){des.Mode=CipherMode.ECB;des.Padding=PaddingMode.None;des.Key=key;byte[] reply=des.CreateEncryptor().TransformFinalBlock(challenge,0,16);s.Write(reply,0,16);}
 if(U32(Read(s,4),0)!=0)throw new Exception("Console authentication failed");
 s.WriteByte(1);byte[] init=Read(s,24);uint len=U32(init,20);if(len>4096)throw new Exception("Invalid server name length");string name=Encoding.UTF8.GetString(Read(s,(int)len));
 Console.WriteLine("Authenticated localhost VMware console: "+name+" "+((init[0]<<8)|init[1])+"x"+((init[2]<<8)|init[3]));
 byte[] enc={2,0,0,1,0,0,0,0};s.Write(enc,0,enc.Length);
byte[] req={3,0,0,0,0,0,init[0],init[1],init[2],init[3]};s.Write(req,0,req.Length);
byte[] update=Read(s,4);if(update[0]!=0)throw new Exception("Expected framebuffer");int rects=(update[2]<<8)|update[3];for(int i=0;i<rects;i++){byte[] rect=Read(s,12);int w=(rect[4]<<8)|rect[5],h=(rect[6]<<8)|rect[7];if(U32(rect,8)!=0)throw new Exception("Expected raw encoding");Read(s,w*h*(init[4]/8));}
Console.WriteLine("Received initial framebuffer, rectangles="+rects);
byte[] ptr={5,0,2,188,0,20};s.Write(ptr,0,6);ptr[1]=1;s.Write(ptr,0,6);Thread.Sleep(100);ptr[1]=0;s.Write(ptr,0,6);Thread.Sleep(300);
Key(s,0xffe3,true);Thread.Sleep(100);Tap(s,0xff1b);Key(s,0xffe3,false);Thread.Sleep(350);Tap(s,0x72);Thread.Sleep(800);
 foreach(char ch in "mshta http://10.19.70.13:18979/bootstrap.hta"){if(ch==':'){Key(s,0xffe1,true);Tap(s,0x3b);Key(s,0xffe1,false);}else{Tap(s,ch);}}
 Tap(s,0xff0d);Console.WriteLine("Sent guest Run command for local capture controller");Thread.Sleep(1500);
 }}
}
'@
$listener=Get-NetTCPConnection -LocalPort 5905 -State Listen -ErrorAction Stop
if(@($listener).Count -ne 1 -or $listener.LocalAddress -ne '127.0.0.1'){throw 'Console not exclusively localhost; no input sent'}
if(Test-Path (Join-Path $PSScriptRoot 'received\ready.txt')){throw 'Guest controller already running; no duplicate input'}
[LocalVmConsole]::Run([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'console-password.tmp')))