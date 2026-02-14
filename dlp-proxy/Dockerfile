FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.* \
    uvicorn[standard]==0.34.* \
    httpx==0.28.* \
    google-cloud-dlp==3.* \
    google-auth==2.* \
    && rm -rf /root/.cache/pip

RUN mkdir -p /data/tokens && chown nobody:nogroup /data/tokens

COPY main.py .

EXPOSE 8080

USER nobody

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
