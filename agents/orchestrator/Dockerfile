# AgentCore Runtime requires an ARM64 container.
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py router.py a2a_client.py approval_client.py ./

# The HTTP protocol contract on AgentCore Runtime requires listening on
# 0.0.0.0:8080 with POST /invocations and GET /ping -- BedrockAgentCoreApp.run()
# (called from main.py) implements both by default.
EXPOSE 8080

CMD ["python", "main.py"]
