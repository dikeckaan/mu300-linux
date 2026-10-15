"""Compile the actual patch's association bridge with explicit upstream stubs."""
from pathlib import Path
import sys
base = Path(__file__).parent
repo = base.parents[1]
outdir = Path(sys.argv[1]).resolve()
outdir.mkdir(parents=True, exist_ok=True)
patch = (repo / 'openwrt/sae-offload/999-unisoc-sae-offload.patch').read_text(encoding='utf-8')
added = '\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))
helper = added[added.index('static bool unisoc_sae_offload_enabled'):].split('#endif', 1)[0]
block = added[added.index('  if ((hapd->iface->drv_flags2'):].split('#endif', 1)[0]
prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
#define os_strcmp strcmp
#define os_memcmp memcmp
#define os_memcmp_const memcmp
#define os_memcpy memcpy
#define os_free free
#define os_zalloc(n) calloc(1,n)
#define wpa_printf(...) ((void)0)
#define WPA_DRIVER_FLAGS2_SAE_OFFLOAD_AP 1
#define SAE_PWE_HUNT_AND_PECK 0
#define WLAN_STATUS_UNSPECIFIED_FAILURE 1
#define WLAN_REASON_UNSPECIFIED 1
#define WLAN_STATUS_INVALID_PMKID 53
#define WLAN_REASON_INVALID_PMKID 49
#define WLAN_STATUS_INVALID_IE 40
#define WLAN_REASON_INVALID_IE 13
#define WLAN_STA_MFP 1
#define WLAN_AUTH_SAE 3
#define WLAN_AUTH_OPEN 0
#define WPA_KEY_MGMT_SAE 1024
#define PMK_LEN 32
#define PMKID_LEN 16
struct sm { bool sae, ft, cache; };
struct sae { u8 pmk[32], pmkid[16]; size_t pmk_len; int akmp; };
struct iface { int drv_flags2; };
struct conf { int sae_pwe; };
struct ap { struct iface *iface; struct conf *conf; void *wpa_auth; };
struct sta { struct sm *wpa_sm; int flags, auth_alg; struct sae *sae; u8 addr[6]; int vlan_id; };
struct elements { const u8 *rsn_ie; size_t rsn_ie_len; };
struct wpa_ie_data { int key_mgmt; size_t num_pmkid; const u8 *pmkid; };
static struct wpa_ie_data parsed;
static int imports, parse_rc;
static bool wpa_auth_uses_sae(struct sm *s) { return s->sae; }
static bool wpa_auth_uses_ft_sae(struct sm *s) { return s->ft; }
static void *wpa_auth_sta_get_pmksa(struct sm *s) { return s->cache ? s : NULL; }
static void sae_clear_data(struct sae *s) { memset(s,0,sizeof(*s)); }
static int wpa_parse_wpa_ie_rsn(const u8 *p, size_t n, struct wpa_ie_data *r) { (void)p; (void)n; *r=parsed; return parse_rc; }
static void wpa_auth_add_sae_pmkid(struct sm *s, const u8 *p) { (void)s; (void)p; imports++; }
static void wpa_auth_pmksa_add_sae(void *a,const u8 *b,const u8 *c,size_t d,const u8 *e,int f,bool g,int h) { (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h; }
'''
suffix = r'''
static unsigned checks;
static void check(bool ok,const char *name) { if(!ok) { fprintf(stderr,"FAIL: %s\n",name); exit(1); } checks++; }
int main(void) {
 struct iface iface={1}; struct conf conf={2}; struct ap ap={&iface,&conf,NULL};
 struct sm sm={0}; struct sta sta={.wpa_sm=&sm,.flags=WLAN_STA_MFP};
 u8 rsn[4]={0}, record[108]={221,52,0x40,0x45,0xda,4}, id[16];
 struct elements elems={rsn+2,2};
 memset(record+6,0xaa,32); memset(record+38,0xbb,16); memset(id,0xbb,16);
 parsed=(struct wpa_ie_data){WPA_KEY_MGMT_SAE,1,id};
 setenv("U30AIR_SAE_OFFLOAD","pmk-first-v1",1);
 check(bridge(&ap,&sta,elems,NULL,0)==0 && imports==0,"PSK accepts residual PWE2");
 sm.sae=true;
 check(bridge(&ap,&sta,elems,record,54)!=0 && imports==0,"SAE PWE2 fails closed");
 conf.sae_pwe=0;
 check(bridge(&ap,&sta,elems,record,54)==0 && imports==1 && sta.sae && sta.sae->pmk_len==32 && !memcmp(sta.sae->pmk,record+6,32) && sta.flags==WLAN_STA_MFP,"SAE imports exact key without authorizing station");
 check(bridge(&ap,&sta,elems,NULL,0)==53 && sta.sae==NULL && sta.auth_alg==WLAN_AUTH_OPEN,"missing fresh result rejects and clears stale SAE");
 sm.cache=true;
 check(bridge(&ap,&sta,elems,NULL,0)==0,"valid upstream PMKSA permits cached path");
 sm.cache=false; id[0]^=1;
 check(bridge(&ap,&sta,elems,record,54)==53 && imports==1,"PMKID mismatch rejected"); id[0]^=1;
 check(bridge(&ap,&sta,elems,record,53)==53,"truncated record rejected");
 memcpy(record+54,record,54);
 check(bridge(&ap,&sta,elems,record,108)==53,"duplicate result rejected");
 check(bridge(&ap,&sta,elems,record,54)==0,"fresh SAE context restored");
 sm.sae=false; conf.sae_pwe=2;
 check(bridge(&ap,&sta,elems,NULL,0)==0 && !sta.sae && sta.auth_alg==WLAN_AUTH_OPEN,"SAE to PSK clears imported state");
 sm.sae=true; unsetenv("U30AIR_SAE_OFFLOAD");
 check(bridge(&ap,&sta,elems,NULL,0)==0,"no opt-in leaves upstream path unchanged");
 setenv("U30AIR_SAE_OFFLOAD","pmk-first-v1",1); iface.drv_flags2=0;
 check(bridge(&ap,&sta,elems,NULL,0)==0,"no driver capability leaves upstream path unchanged");
 printf("PASS: %u bridge state checks from actual patch; RSN parser/cache explicitly stubbed\n",checks);
 return 0;
}
'''
program=prefix+helper+'\nstatic int bridge(struct ap *hapd,struct sta *sta,struct elements elems,const u8 *req_ies,size_t req_ies_len) { int status=0,reason=0;\n'+block+'\n return 0; fail: (void)reason; return status ? status : -1; }\n'+suffix
(outdir/'sae-bridge-state-check.c').write_text(program,newline='\n')
# Negative control must fail the first regression check.
(outdir/'sae-bridge-state-old-guard.c').write_text(program.replace('wpa_auth_uses_sae(sta->wpa_sm) &&\n       hapd->conf->sae_pwe', 'hapd->conf->sae_pwe'),newline='\n')
print('Prepared actual bridge and old-guard negative control')
