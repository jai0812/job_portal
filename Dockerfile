# Job Portal · built by JAI SHARMA
# Container for running the portal on a server. See DEPLOY.md.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY config ./config
COPY scripts ./scripts
# data/ (job database, your applied history, notes) lives on a volume so it survives restarts
VOLUME /app/data
ENV PORTAL_HOST=0.0.0.0 PORT=8787 TRUST_PROXY=1
EXPOSE 8787
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
