const state = { domain: null, resumeToken: null, referenceId: null, toolName: null };

const el = (id) => document.getElementById(id);
const nodes = ["user", "orchestrator", "delegate", "gateway", "interceptor", "approval", "mcp", "result"];

function setTrace(statuses) {
  for (const name of nodes) {
    const node = document.querySelector(`.trace-node[data-node="${name}"]`);
    node.classList.remove("active", "done", "blocked");
    if (statuses[name]) node.classList.add(statuses[name]);
  }
}

function showPanel(id, visible) {
  el(id).hidden = !visible;
}

function showStatus(text) {
  showPanel("status-panel", true);
  el("status-text").textContent = text;
}

function showResult(text) {
  showPanel("result-panel", true);
  el("result-text").textContent = text || "(no response text)";
}

async function postJSON(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.response || `Request to ${url} failed (${res.status})`);
  return data;
}

async function checkHealth() {
  const pill = el("backend-status");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.ready) {
      pill.textContent = `backend ready (${data.region})`;
      pill.className = "pill pill-ok";
    } else {
      pill.textContent = "backend NOT configured -- set ORCHESTRATOR_ARN/APPROVAL_AGENT_ARN";
      pill.className = "pill pill-bad";
    }
  } catch {
    pill.textContent = "backend unreachable";
    pill.className = "pill pill-bad";
  }
}

function handleOrchestratorResponse(r) {
  state.domain = r.domain || state.domain;
  state.resumeToken = r.resume_token || null;
  state.referenceId = r.resume_token ? r.resume_token.reference_id : null;
  state.toolName = r.tool_name || state.toolName;

  showPanel("decision-panel", false);

  switch (r.status) {
    case "clarification_needed":
      setTrace({ user: "done", orchestrator: "done" });
      showStatus("Ambiguous question -- no domain matched.");
      showResult(r.response);
      showPanel("verify-panel", false);
      break;
    case "error":
      setTrace({ user: "done", orchestrator: "blocked" });
      showStatus("Error / blocked.");
      showResult(r.response);
      showPanel("verify-panel", false);
      break;
    case "still_pending":
      showStatus(r.response);
      break;
    case "success":
      setTrace({ user: "done", orchestrator: "done", delegate: "done", gateway: "done", interceptor: "done", approval: "done", mcp: "done", result: "done" });
      showStatus(`Completed${r.domain ? " -- routed to " + r.domain : ""}.`);
      showResult(r.response);
      break;
    case "approval_required":
    case "hitl_required":
      setTrace({ user: "done", orchestrator: "done", delegate: "active", gateway: "done", interceptor: "done", approval: "active" });
      showStatus(r.status === "approval_required" ? "Human approval required." : "Human intervention required.");
      showDecisionPanel(r);
      showPanel("verify-panel", false);
      showPanel("result-panel", false);
      break;
    default:
      showStatus(`Unexpected status: ${r.status}`);
  }
}

function showDecisionPanel(r) {
  const isHitl = r.status === "hitl_required";
  el("decision-title").textContent = isHitl ? "Human intervention required" : "Human approval required";
  el("decision-question").textContent = r.response || "";
  el("decision-reference").textContent = state.referenceId || "(none)";
  el("decision-tool").textContent = state.toolName || "(unknown)";
  showPanel("instruction-row", isHitl);
  showPanel("decision-panel", true);
}

async function submitDecision(decision, instructionText) {
  if (!state.referenceId || !state.resumeToken) return;
  showPanel("decision-panel", false);
  showStatus(`Recording decision: ${decision}...`);

  let r2;
  try {
    r2 = await postJSON("/api/decide", {
      reference_id: state.referenceId,
      decision,
      instruction_text: instructionText || null,
      resume_token: state.resumeToken,
    });
  } catch (err) {
    showStatus("Decision/resume failed.");
    showResult(String(err));
    return;
  }

  const domainForVerify = state.domain;
  const toolForVerify = state.toolName;
  const startMs = r2._trigger_start_ms || Date.now();

  handleOrchestratorResponse(r2);

  if (toolForVerify) {
    runVerification(domainForVerify, toolForVerify, startMs, decision);
  }
}

async function runVerification(domain, toolName, startMs, decision) {
  showPanel("verify-panel", true);
  el("verify-badge").className = "badge badge-unknown";
  el("verify-badge").textContent = "checking (waiting for CloudWatch Logs to ingest)...";
  el("verify-detail").textContent = "";

  await new Promise((r) => setTimeout(r, 9000));

  try {
    const params = new URLSearchParams({ domain, tool_name: toolName, start_ms: String(startMs), decision });
    const res = await fetch(`/api/verify?${params}`);
    const data = await res.json();
    const labels = { EXECUTED: "EXECUTED", NOT_EXECUTED: "NOT EXECUTED / BLOCKED", UNKNOWN: "UNKNOWN" };
    el("verify-badge").className = `badge badge-${data.verdict.toLowerCase()}`;
    el("verify-badge").textContent = labels[data.verdict] || data.verdict;
    el("verify-detail").textContent = data.detail;
  } catch (err) {
    el("verify-badge").className = "badge badge-unknown";
    el("verify-badge").textContent = "UNKNOWN";
    el("verify-detail").textContent = String(err);
  }
}

el("submit-btn").addEventListener("click", async () => {
  const prompt = el("prompt").value.trim();
  if (!prompt) return;

  showPanel("decision-panel", false);
  showPanel("verify-panel", false);
  showPanel("result-panel", false);
  setTrace({ user: "done", orchestrator: "active" });
  showStatus("Sending to Orchestrator...");

  try {
    const r = await postJSON("/api/ask", { prompt });
    handleOrchestratorResponse(r);
  } catch (err) {
    setTrace({ user: "done", orchestrator: "blocked" });
    showStatus("Request failed.");
    showResult(String(err));
  }
});

el("approve-btn").addEventListener("click", () => submitDecision("approve"));
el("deny-btn").addEventListener("click", () => submitDecision("deny"));
el("instruct-btn").addEventListener("click", () => {
  const text = el("instruction-text").value.trim();
  if (!text) return;
  submitDecision("instruction", text);
});

checkHealth();
