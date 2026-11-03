#include "capture_protocol.h"
#include <string.h>
static uint16_t be16(const unsigned char *p) {return (uint16_t)((p[0]<<8)|p[1]);}
static uint32_t be32(const unsigned char *p) {return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static int prefix(const unsigned char *p, size_t n, const char *s, size_t sn) {return n>=sn && memcmp(p,s,sn)==0;}
int cap_decode_ethernet(const unsigned char *f, size_t n, cap_packet *p) {
 static const char cmd[]="Spectra-Physics:CMD_ECLIPSE,";
 static const char reply[]="Spectra-Physics:REPLY_ECLIPSE:";
 size_t off=14, ihl, total, ulen, k; unsigned eth, vlan=0;
 memset(p,0,sizeof(*p));
 if(n<14) return 0;
 eth=be16(f+12);
 while(eth==0x8100 || eth==0x88a8) {
  if(++vlan>2 || n<off+4) return 0;
  eth=be16(f+off+2); off+=4;
 }
 if(eth!=0x0800 || n<off+20 || (f[off]>>4)!=4) return 0;
 ihl=(f[off]&15)*4; total=be16(f+off+2);
 if(ihl<20 || total<ihl+8 || n<off+total || f[off+9]!=17 || (be16(f+off+6)&0x3fff)) return 0;
 p->src_ip=be32(f+off+12); p->dst_ip=be32(f+off+16);
 off+=ihl;
 p->src_port=be16(f+off); p->dst_port=be16(f+off+2);
 ulen=be16(f+off+4);
 if((p->src_port!=1024 && p->dst_port!=1024) || ulen<8 || ulen>total-ihl) return 0;
 p->payload=f+off+8; p->payload_len=(uint32_t)ulen-8;
 if(prefix(p->payload,p->payload_len,cmd,sizeof(cmd)-1)) {
  p->kind=CAP_COMMAND; k=sizeof(cmd)-1;
  /* Every nonempty command line must start with [decimal-tag]. A malformed
     original command blocks UI, even if a later token looks like a query. */
  while(k<p->payload_len) {
   unsigned tag=0, digits=0;
   while(k<p->payload_len && (p->payload[k]=='\r'||p->payload[k]=='\n')) k++;
   if(k==p->payload_len) break;
   if(p->payload[k++]!='[') {p->malformed_command=1; break;}
   while(k<p->payload_len && p->payload[k]>='0' && p->payload[k]<='9') {
    if(++digits>8) {p->malformed_command=1;break;}
    tag=tag*10+(p->payload[k++]-'0');
   }
   if(p->malformed_command || !digits || k>=p->payload_len || p->payload[k++]!=']') {p->malformed_command=1;break;}
   if(!p->tag) p->tag=tag;
   if(tag<1000) p->malformed_command=1;
   if(tag>=2000) {if(!p->write_commands)p->first_write_tag=tag; p->write_commands++;}
   if(k>=p->payload_len || p->payload[k]=='\r'||p->payload[k]=='\n') p->malformed_command=1;
   while(k<p->payload_len && p->payload[k]!='\r' && p->payload[k]!='\n') k++;
  }
  if(!p->tag) p->malformed_command=1;
 } else if(prefix(p->payload,p->payload_len,reply,sizeof(reply)-1)) {
  p->kind=CAP_RESPONSE; k=sizeof(reply)-1;
  if(k<p->payload_len && p->payload[k++]=='<') {
   unsigned digits=0,tag=0;
   while(k<p->payload_len && p->payload[k]>='0' && p->payload[k]<='9' && digits<8) {tag=tag*10+p->payload[k++]-'0';digits++;}
   if(digits && k<p->payload_len && p->payload[k]=='>') p->tag=tag;
  }
 }
 return 1;
}
void cap_observe(cap_observation *o,const cap_packet *p,unsigned iface,int slocal,int dlocal,uint32_t now) {
 unsigned i; cap_pair key,*q;
 if(p->kind==CAP_COMMAND) {
  if(p->write_commands) {if(!o->any_write_commands)o->first_write_tag=p->first_write_tag;o->any_write_commands+=p->write_commands;}
  o->malformed_commands+=p->malformed_command;
 }
 if((p->kind==CAP_COMMAND&&!slocal)||(p->kind==CAP_RESPONSE&&!dlocal)||!p->kind||p->src_ip==p->dst_ip) return;
 memset(&key,0,sizeof(key));key.interface_id=iface;
 if(p->kind==CAP_COMMAND) {key.client_ip=p->src_ip;key.client_port=p->src_port;key.controller_ip=p->dst_ip;key.controller_port=p->dst_port;o->command_packets++;}
 else {key.client_ip=p->dst_ip;key.client_port=p->dst_port;key.controller_ip=p->src_ip;key.controller_port=p->src_port;o->response_packets++;}
 for(i=0;i<o->pair_count;i++) {
  q=o->pairs+i;
  if(q->interface_id==key.interface_id&&q->client_ip==key.client_ip&&q->client_port==key.client_port&&q->controller_ip==key.controller_ip&&q->controller_port==key.controller_port) break;
 }
 if(i==o->pair_count) {if(i==CAP_MAX_PAIRS){o->pair_overflow=1;return;}o->pairs[i]=key;o->pair_count++;}
 q=o->pairs+i;
 if(p->kind==CAP_COMMAND) {q->commands++;q->last_command_ms=now;}
 else {q->responses++;q->last_response_ms=now;}
}
int cap_pair_ready(const cap_observation *o,uint32_t now) {
 const cap_pair *p=o->pairs;
 return !o->any_write_commands&&!o->malformed_commands&&!o->pair_overflow&&o->pair_count==1&&p->commands>=3&&p->responses>=3&&(uint32_t)(now-p->last_command_ms)<=5000&&(uint32_t)(now-p->last_response_ms)<=5000;
}
