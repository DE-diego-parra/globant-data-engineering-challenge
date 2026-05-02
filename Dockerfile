FROM python:3.11-slim as builder

WORKDIR /build
COPY app/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

RUN useradd -m -u 1000 appuser && \
    apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY app/main.py .

RUN chown -R appuser:appuser /app
USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]
