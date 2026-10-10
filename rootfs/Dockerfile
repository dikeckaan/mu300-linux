# Ubuntu 24.04 LTS arm64 root filesystem for the MU300 (exported with `docker export`, not run as a container).
# BASE swaps the distribution: any arm64 Debian-family image with the same package names works, for example
#   docker build --build-arg BASE=debian:13 -t mu300-debian:13 rootfs/
#   docker build --build-arg BASE=kalilinux/kali-rolling -t mu300-kali rootfs/
ARG BASE=ubuntu:24.04
FROM ${BASE}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv systemd-timesyncd systemd-resolved udev dbus kmod \
    iproute2 iputils-ping net-tools nftables dnsmasq-base ethtool \
    openssh-server busybox-static \
    wpasupplicant hostapd iw wireless-regdb rfkill bluez \
    i2c-tools gpiod jq wireguard-tools \
    ca-certificates openssl alsa-utils curl wget nano vim-tiny less htop sudo bash-completion \
    libcap2-bin locales tzdata e2fsprogs dosfstools file procps psmisc lsof strace usbutils pciutils \
 && rm -rf /var/lib/apt/lists/*
RUN sed -i 's/^# *\(en_US.UTF-8\|tr_TR.UTF-8\)/\1/' /etc/locale.gen && locale-gen \
 && ln -sf /usr/share/zoneinfo/Europe/Istanbul /etc/localtime && echo Europe/Istanbul > /etc/timezone \
 && echo mu300 > /etc/hostname \
 && (id ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu) \
 && usermod -aG sudo ubuntu && echo 'ubuntu:ubuntu' | chpasswd \
 && printf 'LABEL=mu300root / ext4 defaults,noatime 0 1\n' > /etc/fstab
