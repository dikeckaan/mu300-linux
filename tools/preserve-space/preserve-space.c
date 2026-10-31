/* Experimental online shrink for the shared U30 Air/M3 layout, measured on MU5352/B18.
 * No format, BLKRRPART, boot-control write or reboot. Build as static aarch64 Linux.
 * The host and this helper independently construct the GPT change before applying it.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/utsname.h>
#include <unistd.h>

#define DISK_SECTORS UINT64_C(61079552)
#define UD_FIRST UINT64_C(12275712)
#define OLD_LAST UINT64_C(61075455)
#define NEW_LAST UINT64_C(52678655)
#define OLD_BLOCKS UINT64_C(6099968)
#define NEW_BLOCKS UINT64_C(5050368)
#define HEAD_BYTES (34*512)
#define TAIL_BYTES (33*512)
#define TAIL_OFFSET ((off_t)(DISK_SECTORS-33)*512)
#define F2FS_MAGIC 0xf2f52010U
#define F2FS_RESIZE_FS _IOW(0xf5, 16, uint64_t)
#define BLKGETSIZE64 _IOR(0x12, 114, size_t)
#define BLKSSZGET _IO(0x12, 104)

_Noreturn static void stop(const char *why) {
    fprintf(stderr,"STOP: %s (errno=%d: %s)\n",why,errno,strerror(errno)); exit(1);
}
static void require(int ok,const char *why) { if (!ok) stop(why); }
static uint32_t u32(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static uint64_t u64(const unsigned char *p) { return (uint64_t)u32(p)|(uint64_t)u32(p+4)<<32; }
static void put32(unsigned char *p,uint32_t v) { for(int i=0;i<4;i++) p[i]=(unsigned char)(v>>(8*i)); }
static void put64(unsigned char *p,uint64_t v) { for(int i=0;i<8;i++) p[i]=(unsigned char)(v>>(8*i)); }
static uint32_t crc(const unsigned char *p,size_t n) {
    uint32_t c=~0U;
    while(n--) { c^=*p++; for(int b=0;b<8;b++) c=(c>>1)^(0xedb88320U&(0U-(c&1U))); }
    return ~c;
}
static void read_at(int fd,void *data,size_t n,off_t off) {
    unsigned char *p=data;
    while(n) {
        ssize_t r=pread(fd,p,n,off);
        if(r<0 && errno==EINTR) continue;
        require(r>0,"short/failed read"); n-=(size_t)r; p+=r; off+=r;
    }
}
static void read_file(const char *path,void *data,size_t n) {
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW); struct stat st;
    require(fd>=0 && !fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_size==(off_t)n,"exact regular input file required");
    read_at(fd,data,n,0); close(fd);
}
static uint64_t number(const char *path) {
    FILE *f=fopen(path,"r"); unsigned long long n=0;
    require(f && fscanf(f,"%llu",&n)==1,"read sysfs number"); fclose(f); return n;
}
static void line(const char *path,char *out,size_t n) {
    FILE *f=fopen(path,"r"); require(f && fgets(out,(int)n,f),"read identity");
    fclose(f); out[strcspn(out,"\r\n")]=0;
}
static void property(const char *key,char *value,size_t n) {
    char cmd[160];
    snprintf(cmd,sizeof(cmd),"/system/bin/getprop %s",key);
    FILE *f=popen(cmd,"r"); require(f && fgets(value,(int)n,f),"Android property unavailable");
    require(pclose(f)==0,"getprop failed"); value[strcspn(value,"\r\n")]=0;
}
static int supported(const char *model,const char *device,const char *platform,const char *kernel) {
    const char *prefix="5.4.254-android12-9-";
    return !strcmp(platform,"ums9620") && !strncmp(kernel,prefix,strlen(prefix)) &&
        ((!strcmp(model,"MU5352") && !strcmp(device,"MU5352")) ||
         (!strcmp(device,"U30Air") && (!strcmp(model,"U30Air") || !strcmp(model,"U30_Air") || !strcmp(model,"U30 Air"))));
}
static uint64_t geometry(int fd) {
    unsigned char a[108],b[108]; read_at(fd,a,sizeof(a),1024); read_at(fd,b,sizeof(b),5120);
    require(!memcmp(a,b,sizeof(a)) && u32(a)==F2FS_MAGIC,"F2FS superblocks disagree");
    uint64_t blocks=u64(a+36); require(blocks==OLD_BLOCKS || blocks==NEW_BLOCKS,"unrecognized F2FS size");
    uint32_t sections=blocks==OLD_BLOCKS?11831:9781;
    require(u32(a+16)==12 && u32(a+20)==9 && u32(a+24)==1 && u32(a+28)==1 &&
        u32(a+44)==sections && u32(a+48)==sections+82 && u32(a+68)==sections &&
        u32(a+92)==42496 && (uint64_t)u32(a+92)+(uint64_t)sections*512==blocks,"unsupported F2FS geometry");
    return blocks;
}
static void header(unsigned char *buf,size_t off,uint64_t cur,uint64_t backup,uint64_t array) {
    unsigned char *h=buf+off; unsigned char tmp[92];
    require(!memcmp(h,"EFI PART",8) && u32(h+8)==0x10000 && u32(h+12)==92 && u32(h+20)==0 &&
        u64(h+24)==cur && u64(h+32)==backup && u64(h+40)==34 && u64(h+48)==OLD_LAST &&
        u64(h+72)==array && u32(h+80)==128 && u32(h+84)==128,"unsupported GPT header");
    memcpy(tmp,h,92); put32(tmp+16,0); require(crc(tmp,92)==u32(h+16),"GPT header CRC");
}
static void validate_gpt(unsigned char *h,unsigned char *t,uint64_t last) {
    header(h,512,1,DISK_SECTORS-1,2); header(t,32*512,DISK_SECTORS-1,1,DISK_SECTORS-33);
    require(!memcmp(h+512+56,t+32*512+56,16),"GPT disk GUID mismatch");
    require(!memcmp(h+1024,t,128*128),"GPT entry arrays disagree");
    require(crc(h+1024,128*128)==u32(h+512+88) && crc(t,128*128)==u32(t+32*512+88),"GPT entries CRC");
    require(h[510]==0x55 && h[511]==0xaa && h[450]==0xee,"protective MBR required");
    uint64_t previous=33;
    for(int i=0;i<128;i++) {
        unsigned char *e=h+1024+i*128; unsigned char zero[16]={0};
        if(i>=75) { require(!memcmp(e,zero,16),"unexpected trailing partition"); continue; }
        require(memcmp(e,zero,16)!=0 && u64(e+32)>previous && u64(e+40)>=u64(e+32) &&
            u64(e+40)<=OLD_LAST,"partition ordering, bounds or overlap"); previous=u64(e+40);
        if(i==74) {
            unsigned char name[72]={0}; const char *s="userdata";
            for(int k=0;s[k];k++) name[k*2]=(unsigned char)s[k];
            require(!memcmp(e+56,name,72) && u64(e+32)==UD_FIRST && u64(e+40)==last,"userdata must be the last partition in the measured layout");
        }
    }
}
static void edit(unsigned char *buf,size_t hdr,size_t entries) {
    put64(buf+entries+74*128+40,NEW_LAST);
    put32(buf+hdr+88,crc(buf+entries,128*128)); put32(buf+hdr+16,0);
    put32(buf+hdr+16,crc(buf+hdr,92));
}
static void plan(unsigned char *h,unsigned char *t,unsigned char *nh,unsigned char *nt) {
    validate_gpt(h,t,OLD_LAST); memcpy(nh,h,HEAD_BYTES); memcpy(nt,t,TAIL_BYTES);
    edit(nh,512,1024); edit(nt,32*512,0); validate_gpt(nh,nt,NEW_LAST);
}
static void match(int fd,const unsigned char *want,size_t n,off_t off) {
    unsigned char actual[HEAD_BYTES]; require(n<=sizeof(actual),"internal read bound");
    read_at(fd,actual,n,off); require(!memcmp(actual,want,n),"live GPT does not match plan; do not retry writes blindly");
}
static void write_at(int fd,const unsigned char *p,size_t n,off_t off) {
    while(n) {
        ssize_t r=pwrite(fd,p,n,off); if(r<0 && errno==EINTR) continue;
        require(r>0,"GPT write failed; inspect both copies before recovery"); n-=(size_t)r; p+=r; off+=r;
    }
    require(!fsync(fd),"GPT flush failed; inspect both copies");
}
static void commit(int fd,const unsigned char *h,const unsigned char *t,const unsigned char *nh,const unsigned char *nt) {
    match(fd,h,HEAD_BYTES,0); match(fd,t,TAIL_BYTES,TAIL_OFFSET);
    puts("WRITING_BACKUP_GPT_FIRST"); write_at(fd,nt,TAIL_BYTES,TAIL_OFFSET); match(fd,nt,TAIL_BYTES,TAIL_OFFSET);
    puts("BACKUP_GPT_FLUSHED_AND_VERIFIED");
    write_at(fd,nh+1024,32*512,1024); write_at(fd,nh+512,512,512);
    match(fd,nh,HEAD_BYTES,0); match(fd,nt,TAIL_BYTES,TAIL_OFFSET);
    puts("BOTH_GPT_COPIES_FLUSHED_AND_VERIFIED_REBOOT_REQUIRED");
}
struct device { int data,raw,disk; uint64_t blocks,sectors; struct statfs fs; };
static struct device inspect(void) {
    require(geteuid()==0,"root required");
    char model[256],device[256],platform[256];
    property("ro.product.model",model,sizeof(model)); property("ro.product.device",device,sizeof(device));
    property("ro.board.platform",platform,sizeof(platform));
    struct utsname u; require(!uname(&u) && supported(model,device,platform,u.release),"unsupported U30 Air/M3 Android profile");
    require(number("/sys/block/mmcblk0/size")==DISK_SECTORS &&
        number("/sys/class/block/mmcblk0p75/start")==UD_FIRST,"unsupported eMMC geometry");
    struct device d; d.sectors=number("/sys/class/block/mmcblk0p75/size");
    require(d.sectors==OLD_LAST-UD_FIRST+1 || d.sectors==NEW_LAST-UD_FIRST+1,"unsupported userdata size");
    char ud[PATH_MAX]; require(realpath("/dev/block/by-name/userdata",ud) && !strcmp(ud,"/dev/block/mmcblk0p75"),"unexpected userdata partition");
    d.data=open("/data",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    struct stat m; require(d.data>=0 && !fstat(d.data,&m) && !fstatfs(d.data,&d.fs) &&
        (uint32_t)d.fs.f_type==F2FS_MAGIC && d.fs.f_bsize==4096,"mounted /data is not the expected F2FS");
    /* Bind mounts can make df name an APK. Match the actual /data device number instead. */
    DIR *dir=opendir("/sys/block"); require(dir!=NULL,"read block devices");
    struct dirent *e; d.raw=-1;
    while((e=readdir(dir))) {
        if(strncmp(e->d_name,"dm-",3)) continue;
        char path[PATH_MAX]; snprintf(path,sizeof(path),"/dev/block/%s",e->d_name);
        struct stat st; if(stat(path,&st) || !S_ISBLK(st.st_mode) || st.st_rdev!=m.st_dev) continue;
        char name[80]; snprintf(path,sizeof(path),"/sys/block/%s/dm/name",e->d_name); line(path,name,sizeof(name));
        require(!strcmp(name,"userdata"),"/data mapper is not userdata");
        snprintf(path,sizeof(path),"/sys/block/%s/slaves",e->d_name);
        DIR *slaves=opendir(path); require(slaves!=NULL,"read mapper backing device"); int count=0; struct dirent *s;
        while((s=readdir(slaves))) if(s->d_name[0]!='.') { require(!strcmp(s->d_name,"mmcblk0p75"),"unsupported mapper backing device"); count++; }
        closedir(slaves); require(count==1,"unsupported mapper chain");
        snprintf(path,sizeof(path),"/dev/block/%s",e->d_name); d.raw=open(path,O_RDONLY|O_CLOEXEC); break;
    }
    closedir(dir); require(d.raw>=0,"no mapper matching mounted /data"); d.blocks=geometry(d.raw);
    require(d.blocks*4096<=d.sectors*512,"filesystem exceeds userdata partition");
    d.disk=open("/dev/block/mmcblk0",O_RDONLY|O_CLOEXEC); uint64_t bytes=0; int sector=0;
    require(d.disk>=0 && !ioctl(d.disk,BLKGETSIZE64,&bytes) && bytes==DISK_SECTORS*512 &&
        !ioctl(d.disk,BLKSSZGET,&sector) && sector==512,"disk device size/sector mismatch");
    unsigned char h[HEAD_BYTES],t[TAIL_BYTES]; read_at(d.disk,h,sizeof(h),0); read_at(d.disk,t,sizeof(t),TAIL_OFFSET);
    uint64_t last=u64(h+1024+74*128+40); require(last==OLD_LAST || last==NEW_LAST,"unrecognized GPT end");
    validate_gpt(h,t,last);
    char cid[80]; line("/sys/class/block/mmcblk0/device/cid",cid,sizeof(cid));
    require(strlen(cid)==32 && strspn(cid,"0123456789abcdef")==32,"invalid eMMC CID");
    printf("CID=%s\nFS_BLOCKS=%" PRIu64 "\nDATA_SECTORS=%" PRIu64 "\nGPT_LAST=%" PRIu64 "\nAVAILABLE_BLOCKS=%llu\nBATTERY=%" PRIu64 "\n",
        cid,d.blocks,d.sectors,last,(unsigned long long)d.fs.f_bavail,number("/sys/class/power_supply/battery/capacity"));
    return d;
}
int main(int argc,char **argv) {
    setvbuf(stdout,NULL,_IONBF,0);
    require(argc==2 && (!strcmp(argv[1],"inspect") || !strcmp(argv[1],"apply")),"usage: preserve-space inspect|apply (apply in the root-owned prepared directory)");
    struct device d=inspect(); if(!strcmp(argv[1],"inspect")) return 0;
    struct stat st; char cwd[PATH_MAX];
    require(getcwd(cwd,sizeof(cwd)) && !strncmp(cwd,"/data/adb/mu300-preserve-",25) &&
        !stat(".",&st) && st.st_uid==0 && !(st.st_mode&0077),"apply needs its private root-owned state directory");
    int lock=open("/data/adb/mu300-preserve.lock",O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);
    require(lock>=0 && !flock(lock,LOCK_EX|LOCK_NB),"another native apply is active");
    char expected_cid[33],actual_cid[80]; read_file("cid",expected_cid,32); expected_cid[32]=0;
    line("/sys/class/block/mmcblk0/device/cid",actual_cid,sizeof(actual_cid)); require(!strcmp(actual_cid,expected_cid),"plan belongs to another eMMC");
    unsigned char h[HEAD_BYTES],t[TAIL_BYTES],nh[HEAD_BYTES],nt[TAIL_BYTES],candidate[HEAD_BYTES];
    read_file("before.head",h,sizeof(h)); read_file("before.tail",t,sizeof(t)); plan(h,t,nh,nt);
    read_file("candidate.head",candidate,sizeof(nh)); require(!memcmp(candidate,nh,sizeof(nh)),"host/native primary plans differ");
    read_file("candidate.tail",candidate,sizeof(nt)); require(!memcmp(candidate,nt,sizeof(nt)),"host/native backup plans differ");
    match(d.disk,h,sizeof(h),0); match(d.disk,t,sizeof(t),TAIL_OFFSET);
    uint64_t battery=number("/sys/class/power_supply/battery/capacity"); require(battery>=80 && battery<=100,"battery must be at least 80 percent");
    require(d.sectors==OLD_LAST-UD_FIRST+1,"kernel partition size changed");
    if(d.blocks==OLD_BLOCKS) {
        require((uint64_t)d.fs.f_bavail>=OLD_BLOCKS-NEW_BLOCKS+131072,"insufficient free blocks plus reserve");
        require(!syncfs(d.data),"sync before shrink"); uint64_t target=NEW_BLOCKS;
        puts("CALLING_KERNEL_ONLINE_SHRINK_GPT_NOT_TOUCHED");
        require(!ioctl(d.data,F2FS_RESIZE_FS,&target),"online shrink failed; GPT not touched");
        require(!syncfs(d.data),"sync after shrink; GPT not touched");
    }
    require(geometry(d.raw)==NEW_BLOCKS,"smaller F2FS not verified; GPT not touched");
    puts("F2FS_SHRINK_VERIFIED_GPT_NOT_TOUCHED");
    int disk=open("/dev/block/mmcblk0",O_RDWR|O_CLOEXEC); require(disk>=0,"open disk for GPT commit");
    commit(disk,h,t,nh,nt); close(disk); return 0;
}
