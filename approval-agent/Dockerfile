# AgentCore Runtime requires an ARM64 container.
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py deterministic.py semantic.py grants.py state.py ./

# Same HTTP protocol contract as the Orchestrator: listen on
# 0.0.0.0:8080 with POST /invocations and GET /ping, implemented by
# BedrockAgentCoreApp.run() (called from main.py).
EXPOSE 8080

CMD ["python", "main.py"]
