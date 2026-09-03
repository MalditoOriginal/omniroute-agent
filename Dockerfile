FROM python:3.11-slim
RUN apt-get update && apt-get install -y git curl
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir aider-chat
COPY . .
CMD ["python", "api_server.py"]
