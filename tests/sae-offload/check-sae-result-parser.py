"""Exercise malformed/ambiguous firmware-result records without real keys."""
from pathlib import Path
import sys

base = Path(__file__).parent
repo = base.parents[1]
outdir = Path(sys.argv[1]).resolve()
outdir.mkdir(parents=True, exist_ok=True)
patch = (repo/'openwrt/sae-offload/999-unisoc-sae-offload.patch').read_text(encoding='utf-8')
added = '\n'.join(line[1:] for line in patch.splitlines()
                  if line.startswith('+') and not line.startswith('+++'))
start = added.index('static bool unisoc_sae_offload_enabled(')
end = added.index('#endif', start)
helper = added[start:end]
program = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8;
#define os_strcmp strcmp
#define os_memcmp memcmp
'''+helper+r'''
static unsigned int checks;
static void check(bool ok, const char *name) {
 if (!ok) { fprintf(stderr, "FAIL: %s\n", name); exit(1); }
 checks++;
}
int main(void) {
 u8 record[54] = {221,52,0x40,0x45,0xda,4};
 u8 framed[108] = {0};
 unsetenv("U30AIR_SAE_OFFLOAD");
 check(!unisoc_sae_offload_result(record,54), "disabled by default");
 setenv("U30AIR_SAE_OFFLOAD","wrong",1);
 check(!unisoc_sae_offload_result(record,54), "wrong opt-in rejected");
 setenv("U30AIR_SAE_OFFLOAD","pmk-first-v1",1);
 check(unisoc_sae_offload_result(record,54)==record+6, "one terminal result");
 framed[0]=1; framed[1]=1; framed[2]=0;
 memcpy(framed+3,record,54);
 check(unisoc_sae_offload_result(framed,57)==framed+9, "ordinary peer IE before result");
 memcpy(framed,record,54); framed[54]=1; framed[55]=0;
 check(!unisoc_sae_offload_result(framed,56), "nonterminal result rejected");
 memcpy(framed+54,record,54);
 check(!unisoc_sae_offload_result(framed,108), "duplicate results rejected");
 check(!unisoc_sae_offload_result(record,53), "truncated record rejected");
 check(!unisoc_sae_offload_result(NULL,54), "missing buffer rejected");
 check(!unisoc_sae_offload_result(record,1), "trailing partial header rejected");
 record[2]=0;
 check(!unisoc_sae_offload_result(record,54), "foreign vendor rejected");
 record[2]=0x40; record[1]=51;
 check(!unisoc_sae_offload_result(record,54), "wrong record size rejected");
 printf("PASS: %u firmware-result boundary checks; synthetic zero payload only\n",checks);
 return 0;
}
'''
out = outdir/'sae-result-parser-check.c'
out.write_text(program, newline='\n')
print('Prepared synthetic boundary checks from the exact final patch helper')
