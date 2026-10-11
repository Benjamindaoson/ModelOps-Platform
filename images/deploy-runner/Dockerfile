FROM python:3.12-slim-bookworm

ARG KUBECTL_VERSION=v1.31.12
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl" -o /tmp/kubectl \
    && curl -fsSL "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl.sha256" -o /tmp/kubectl.sha256 \
    && echo "$(cat /tmp/kubectl.sha256)  /tmp/kubectl" | sha256sum -c - \
    && install -m 0755 /tmp/kubectl /usr/local/bin/kubectl \
    && rm /tmp/kubectl /tmp/kubectl.sha256 \
    && pip --no-cache-dir install "PyYAML==6.0.2" \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 modelops && useradd --uid 10001 --gid 10001 --create-home modelops
USER 10001
WORKDIR /home/modelops
CMD ["/bin/bash"]
