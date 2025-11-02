FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Base tools
RUN apt-get update && apt-get install -y \
    jdupes \
    exiftool \
    jq \
    bash \
    tzdata \
    coreutils \
    findutils \
    python3 \
    python3-pip \
    python3-numpy \
    python3-pil \
    && rm -rf /var/lib/apt/lists/*
# imagehash via pip (no native deps)
RUN pip install --no-cache-dir ImageHash

ENV TZ=Europe/Berlin
WORKDIR /app

COPY entrypoint.sh /entrypoint.sh
COPY app/similar.py /app/similar.py
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
