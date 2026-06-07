FROM python:3.11-slim

RUN rm -f /usr/bin/pip /usr/bin/pip3 /usr/bin/curl /usr/bin/wget \
    && ln -s /bin/false /usr/local/bin/pip \
    && ln -s /bin/false /usr/local/bin/pip3 \
    && ln -s /bin/false /usr/local/bin/curl \
    && ln -s /bin/false /usr/local/bin/wget

RUN useradd -u 65534 -r -s /bin/false sandbox

WORKDIR /sandbox
COPY runner.py .
RUN chown -R 65534:65534 /sandbox

USER 65534
ENTRYPOINT ["python", "runner.py"]
