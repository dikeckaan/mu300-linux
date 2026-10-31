/* Offline harness. The production helper has no simulated-device option. */
#define main preserve_main
#include "../tools/preserve-space/preserve-space.c"
#undef main

int main(int argc,char **argv) {
    unsigned char h[HEAD_BYTES],t[TAIL_BYTES],nh[HEAD_BYTES],nt[TAIL_BYTES];
    require(argc>=3,"test harness arguments");
    if(!strcmp(argv[1],"profile")) {
        require(argc==6,"profile MODEL DEVICE PLATFORM KERNEL");
        return supported(argv[2],argv[3],argv[4],argv[5])?0:1;
    }
    if(!strcmp(argv[1],"geometry")) {
        int fd=open(argv[2],O_RDONLY); require(fd>=0,"fixture");
        printf("%" PRIu64 "\n",geometry(fd)); return 0;
    }
    require(argc==5,"test harness: plan|commit HEAD TAIL OUT");
    read_file(argv[2],h,sizeof(h)); read_file(argv[3],t,sizeof(t)); plan(h,t,nh,nt);
    if(!strcmp(argv[1],"plan")) {
        int fd=open(argv[4],O_WRONLY|O_CREAT|O_EXCL,0600); require(fd>=0,"new output file");
        write_at(fd,nh,sizeof(nh),0); write_at(fd,nt,sizeof(nt),sizeof(nh)); close(fd); return 0;
    }
    require(!strcmp(argv[1],"commit"),"unknown test command");
    int fd=open(argv[4],O_RDWR|O_NOFOLLOW); struct stat st;
    require(fd>=0 && !fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_size==(off_t)DISK_SECTORS*512,
        "only a regular sparse fixture, never a block device");
    commit(fd,h,t,nh,nt); return 0;
}
