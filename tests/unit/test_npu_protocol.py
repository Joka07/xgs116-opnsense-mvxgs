# SPDX-License-Identifier: MIT
"""Host-only tests compile and execute the actual forwarder wire transforms."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'npu/firmware'

class NpuProtocol(unittest.TestCase):
    def test_nmp_configuration_is_valid_and_has_vlan_headroom(self):
        config = json.loads((FW / 'dp-nmp-config.txt').read_text())
        pf = config['nmp_params']['containers_params-0']['lf_params-0']['nicpf']
        # MUSDK effective PP2 offset adds two Marvell bytes to configured offset.
        self.assertGreaterEqual(pf['dflt_pkt_offset'] + 2, 66)
        self.assertGreaterEqual(pf['port-params-pp2-port']['lcl_bpools_params-1']['buff_size'], 1588 + 66)

    def compile_run(self, source, *flags):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'test.c'
            src.write_text(source)
            exe = Path(d)/'test'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(FW), *flags,
                            str(src), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_real_tag_transform_all_ports_vlan_and_mtu(self):
        self.compile_run(r'''
#include <assert.h>
#include <stdio.h>
#include "tag_dsa.h"
int main(void) {
 unsigned tests=0;
 for (unsigned port=1;port<=9;port++) for (unsigned vlan=0;vlan<3;vlan++)
 for (unsigned tci=0;tci<65536;tci+=257) {
  unsigned ethlen=1514+(vlan?4:0);
  unsigned char original[1600],buf[2048],*wire,*host;
  uint16_t wirelen,hostlen;
  for(unsigned i=0;i<ethlen;i++)original[i]=(unsigned char)i;
  if(vlan) { original[12]=vlan==1?0x81:0x88; original[13]=vlan==1?0:0xa8;
   original[14]=tci>>8; original[15]=tci; original[16]=8; original[17]=0; }
  else {original[12]=8; original[13]=0;}
  unsigned char *f=buf+128;
  memset(f,0,66); f[0]=0x80+port; memcpy(f+66,original,ethlen);
  assert(dp_h2t_transform(f,ethlen+66,&wire,&wirelen)==0);
  assert((wire[12]&31)==DP_DSA_DEV); assert((wire[13]>>3)==port);
  assert((wire[12]>>6)==1);
  /* A switch mirrors FROM_CPU port/device into FORWARD on the same test port. */
  wire[12]=(wire[12]&0x3f)|0xc0;
  assert(dp_t2h_transform(wire,wirelen,wire-buf,NULL,&host,&hostlen)==0);
  assert(hostlen==ethlen+66); assert(host[0]==0x80+port); assert(host[1]==0);
  assert(memcmp(host+66,original,ethlen)==0);
  assert(((struct agnic_pport_md *)(host+2))->orig_l2_len==ethlen);
  tests++;
 }
 printf("PASS: %u real DSA round trips (all ports, 802.1Q/802.1ad, full MTU, PCP/DEI/VID)\n",tests);
 return 0;
}''', '-DDP_DSA_DEV=2')

    def test_malformed_frames_rejected(self):
        self.compile_run(r'''
#include <assert.h>
#include "tag_dsa.h"
int main(void) {
 uint8_t b[512]={0}, *f=b+128,*o; uint16_t n;
 f[0]=0x81;f[1]=1;assert(dp_h2t_transform(f,100,&o,&n)<0);
 f[1]=0;assert(dp_h2t_transform(f,1589,&o,&n)<0);
 f[1]=0;assert(dp_h2t_transform(f,79,&o,&n)<0);
 f[0]=0x80;assert(dp_h2t_transform(f,100,&o,&n)<0);
 f[0]=0x81;f[78]=0x81;f[79]=0;assert(dp_h2t_transform(f,83,&o,&n)<0);
 memset(f,0,100);f[12]=0xc2;f[13]=8;
 assert(dp_t2h_transform(f,1600,128,0,&o,&n)<0);
 assert(dp_t2h_transform(f,17,128,0,&o,&n)<0);
 assert(dp_t2h_transform(f,100,61,0,&o,&n)==-3);
 f[12]=0xe2;assert(dp_t2h_transform(f,100,65,0,&o,&n)==-3);
 f[12]=0xc1;assert(dp_t2h_transform(f,100,128,0,&o,&n)==-5);
 f[12]=0xc2;f[13]=0;assert(dp_t2h_transform(f,100,128,0,&o,&n)==-4);
 f[13]=8|4;assert(dp_t2h_transform(f,100,128,0,&o,&n)==-5);
 f[13]=8;f[12]=0x42;assert(dp_t2h_transform(f,100,128,0,&o,&n)==-5);
 f[12]=0x82;assert(dp_t2h_transform(f,100,128,0,&o,&n)==-5);
 return 0;
}''', '-DDP_DSA_DEV=2')

    def test_independent_dsa_vlan_wire_vector(self):
        self.compile_run(r'''
#include <assert.h>
#include "tag_dsa.h"
int main(void) {
 uint8_t b[512]={0}, *f=b+128,*wire,*host; uint16_t n,hostlen;
 const uint8_t expected[]={0x62,0x19,0xa1,0x23};
 f[0]=0x83; f[66+12]=0x81;f[66+13]=0;f[66+14]=0xb1;f[66+15]=0x23;
 f[66+16]=8; f[66+17]=0;
 assert(dp_h2t_transform(f,66+64,&wire,&n)==0);
 /* IEEE802.1Q TCI b123: PCP5, DEI1, VID0x123. Marvell DSA moves DEI
  * to byte1 bit0; FROM_CPU=01, tagged bit5, device2, physical port3. */
 assert(memcmp(wire+12,expected,4)==0);
 wire[12]=0x22; /* TO_CPU preserves tagged+device fields; reason0. */
 assert(dp_t2h_transform(wire,n,wire-b,NULL,&host,&hostlen)==0);
 const uint8_t vlan[]={0x81,0x00,0xb1,0x23};
 assert(memcmp(host+66+12,vlan,4)==0);
 return 0;
}''', '-DDP_DSA_DEV=2')

    def test_upstream_swop_v2(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d)/'swop'
            subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                            '-fsanitize=undefined','-fno-sanitize-recover=all','-DDP_SWOP_TEST',
                            '-DDP_SWOP_CAP_VERSION=2',str(FW/'dp_swop_test.c'),str(FW/'dp_swop.c'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

    def test_swop_v1_rejects_v2_sfp(self):
        self.compile_run(r'''
#include <assert.h>
#include <string.h>
#include "dp_swop.c"
int main(void) {
 struct dp_swop_req q={.magic=DP_SWOP_MAGIC,.version=1,.op=DP_SWOP_OP_SFP,.dev=9};
 struct dp_swop_resp r;
 assert(DP_SWOP_CAP_VERSION==1); assert(DP_SWOP_CAP_SLOT_OFF==0xf000);
 assert(DP_SWOP_CAP_WINDOW_OFF+DP_SWOP_CAP_SLOT_OFF==0x13000);
 assert(dp_swop_service(&q,sizeof(q),&r,sizeof(r))==56);
 assert(r.magic==DP_SWOP_RESP_MAGIC); assert(r.status==DP_SWOP_E_OP);
 return 0;
}''','-D_DEFAULT_SOURCE','-DDP_SWOP_CAP_VERSION=1')

if __name__ == '__main__':
    unittest.main()
