# Native arm64 or x86_64 cross-build environment for mainline kernels (Ubuntu 26.04 GCC)
FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-aarch64-linux-gnu bc bison flex libssl-dev libelf-dev lz4 cpio kmod python3 curl device-tree-compiler xz-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*
