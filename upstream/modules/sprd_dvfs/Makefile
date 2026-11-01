# DDR and modem DVFS of the vendor 5.4 kernel (parity group dvfs, FINDINGS 234): both talk to the co-processors over
# SIPC, so they need the modem stack's headers and exports (sprd_modem, built before this).
#   sprd_ddr_dvfs: the scene-frequency devfreq device (sprd,ddr-dvfs), pm_sys's DDR DFS
#   sprd_cp_dvfs:  dvfs_pscp / dvfs_phycp (sprd,pscp-dvfs, sprd,phycp-dvfs), the modem's own DVFS controls
obj-m += sprd_ddr_dvfs.o sprd_cp_dvfs.o
sprd_ddr_dvfs-y := sprd_ddr_dvfs_core.o sprd_ddr_dvfs_sp.o sprd_governor_vote.o
# 6.18 keeps the governor interface in drivers/devfreq/governor.h; 7.x has <linux/devfreq-governor.h>
ccflags-y += -I$(src)/../sprd_modem/kinclude -I$(src)/../wcn_bsp/kinclude -I$(srctree)/drivers/devfreq
