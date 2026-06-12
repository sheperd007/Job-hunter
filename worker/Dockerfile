FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Build context is ./worker; keep the package importable as `worker.*`
COPY . ./worker/
EXPOSE 8000
CMD ["uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
