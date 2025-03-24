#! /bin/bash
docker pull ghcr.io/gem5/ubuntu-22.04_all-dependencies:v23-0
docker run -u $UID:$GID --volume /home/minchan/sim/gem5-resources/src/spec-2006/gem5:/gem5 --rm -it ghcr.io/gem5/ubuntu-22.04_all-dependencies:v23-0
