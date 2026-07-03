FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    gcc \
    g++ \
    make \
    nodejs \
    npm \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip pytest
RUN useradd -m -u 1000 sandbox

USER sandbox
WORKDIR /workspace
