FROM docker:29-cli AS docker-cli

FROM python:3.12-slim

WORKDIR /app

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

RUN pip install --no-cache-dir \
      --index-url https://packagefeedproxy.microsoft.io/pypi/simple \
      requests==2.32.3

COPY harness/ /app/

CMD ["python", "-u", "orchestrator.py"]
