# AgentCore Runtime requires an ARM64 container for A2A servers.
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py gateway_tool.py ./

# A2A servers on AgentCore Runtime must listen on 0.0.0.0:9000 at the root
# path -- serve_a2a() in main.py binds there by default.
EXPOSE 9000

CMD ["python", "main.py"]
