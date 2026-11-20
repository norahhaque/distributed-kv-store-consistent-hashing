# Lightweight Alpine Linux with Python already installed
FROM python:3.12-alpine

# Print log lines right away instead of buffering them
ENV PYTHONUNBUFFERED=1

# All following commands run inside /app in the container
WORKDIR /app

# Install dependencies first (Flask), so Docker can reuse this step if only the code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Add the application source code. All .py files, so the same image can run either a
# store (kv_server.py) or the benchmark (kv_bench.py + kv_client.py + hash_ring.py)
COPY *.py .

# The server listens on port 8080
EXPOSE 8080

# Start the server automatically when the container starts
# 0.0.0.0 so requests from outside the container can reach it
CMD ["python", "kv_server.py", "--host", "0.0.0.0", "--port", "8080"]
