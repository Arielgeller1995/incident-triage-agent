"""
Kubernetes triage agent — four tools, real Tavily web search.

Tool overview
─────────────
get_troubleshooting_docs(error_type)
    Reads a Markdown file from the docs/ folder that matches the error type
    (CrashLoopBackOff, OOMKilled, ImagePullBackoff).  Returns the raw Markdown
    so Claude can cite specific steps from the official runbook.

search_web(query)
    Calls the Tavily Search API (tavily-python SDK) and returns the top results
    as JSON.  Useful when the local docs don't cover an edge case or when the
    error message suggests a known upstream bug that might have a public fix.
    Requires TAVILY_API_KEY in the environment.

get_cluster_state(pod_name)
    Returns mock output of `kubectl describe pod <pod_name>`.  Provides the
    full pod spec, conditions, and the Events section — the most important
    surface for diagnosing image pull errors and probe failures.

get_recent_logs(pod_name)
    Returns mock recent log lines for the pod (equivalent to `kubectl logs`).
    Reveals application-level stack traces and OOM signals that aren't visible
    in the describe output.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from tavily import TavilyClient

# ---------------------------------------------------------------------------
# Clients (module-level to avoid re-initialising per request)
# ---------------------------------------------------------------------------

# Anthropic client reads ANTHROPIC_API_KEY from the environment automatically.
_anthropic = anthropic.Anthropic()

# Tavily client reads TAVILY_API_KEY explicitly — fail fast if it is absent.
_tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

# Path to local runbook docs relative to this file.
_DOCS_DIR = Path(__file__).parent / "docs"

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_troubleshooting_docs(error_type: str) -> str:
    """
    Read the Markdown runbook for *error_type* from the docs/ folder.

    File naming convention: docs/<ErrorType>.md
    Falls back to a generic message when no file matches.
    """
    doc_path = _DOCS_DIR / f"{error_type}.md"
    if doc_path.exists():
        content = doc_path.read_text(encoding="utf-8")
        return json.dumps({"error_type": error_type, "doc": content})
    return json.dumps({
        "error_type": error_type,
        "doc": (
            "No local runbook found for this error type. "
            "Use kubectl describe and kubectl logs for manual investigation."
        ),
    })


def search_web(query: str) -> str:
    """
    Run a Tavily web search and return the top results.

    Each result includes title, url, and content snippet so Claude can
    reference specific public resources in its action items.
    """
    response = _tavily.search(query=query, max_results=5)
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in response.get("results", [])
    ]
    return json.dumps({"query": query, "results": results})


def get_cluster_state(pod_name: str) -> str:
    """
    Return mock `kubectl describe pod` output for *pod_name*.

    In production this would shell out to kubectl or call the K8s API.
    The mock is realistic enough for the LLM to extract meaningful signals
    (image name, resource limits, Events).
    """
    mock = f"""\
Name:         {pod_name}
Namespace:    production
Node:         node-1.internal/10.0.1.42
Start Time:   Fri, 20 Mar 2026 08:12:34 +0000
Labels:       app=api-server
Status:       CrashLoopBackOff

Containers:
  api-server:
    Image:          gcr.io/my-project/api-server:v2.3.1
    Port:           8080/TCP
    Limits:
      cpu:     500m
      memory:  256Mi
    Requests:
      cpu:     250m
      memory:  128Mi
    Liveness:   http-get http://:8080/healthz delay=5s timeout=1s period=10s
    Last State: Terminated
      Reason:   OOMKilled
      Exit Code: 137
      Finished:  Fri, 20 Mar 2026 08:14:02 +0000
    Ready:          False
    Restart Count:  7

Conditions:
  Type              Status
  Initialized       True
  Ready             False
  ContainersReady   False
  PodScheduled      True

Events:
  Type     Reason     Age                From     Message
  ----     ------     ---                ----     -------
  Normal   Scheduled  10m                default  Successfully assigned production/{pod_name}
  Normal   Pulling    10m                kubelet  Pulling image "gcr.io/my-project/api-server:v2.3.1"
  Normal   Pulled     10m                kubelet  Successfully pulled image
  Normal   Created    10m                kubelet  Created container api-server
  Warning  OOMKilling 8m (x7 over 10m)  kubelet  Memory limit reached, killed process
"""
    return json.dumps({"pod_name": pod_name, "describe_output": mock})


def get_recent_logs(pod_name: str) -> str:
    """
    Return mock recent log lines for *pod_name* (like `kubectl logs --tail=50`).

    Real implementation would stream from the Kubernetes logs API.
    The mock includes a realistic OOM-adjacent application panic so the LLM
    can correlate log signals with the cluster state.
    """
    mock_lines = [
        f"2026-03-20T08:13:55Z {pod_name} INFO  Starting api-server v2.3.1",
        f"2026-03-20T08:13:56Z {pod_name} INFO  Connecting to postgres://db.internal:5432/prod",
        f"2026-03-20T08:13:56Z {pod_name} INFO  Loading feature flags from config-map...",
        f"2026-03-20T08:13:57Z {pod_name} INFO  Warming up in-memory cache (target: 200 000 entries)",
        f"2026-03-20T08:13:59Z {pod_name} WARN  Cache warm-up at 150 000 entries — memory pressure rising",
        f"2026-03-20T08:14:01Z {pod_name} ERROR runtime: out of memory: cannot allocate 134217728-byte block",
        f"2026-03-20T08:14:01Z {pod_name} ERROR goroutine 1 [running]:",
        f"2026-03-20T08:14:01Z {pod_name} ERROR runtime.throw2({{0x12a3c80, 0xf}})",
        f"2026-03-20T08:14:01Z {pod_name} ERROR \t/usr/local/go/src/runtime/panic.go:1 +0x5c",
        f"2026-03-20T08:14:02Z {pod_name} ERROR container killed by OOM killer (exit code 137)",
    ]
    return json.dumps({"pod_name": pod_name, "log_lines": mock_lines})


# ---------------------------------------------------------------------------
# Tool schemas (passed to Anthropic so Claude knows when/how to call each)
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "get_troubleshooting_docs",
        "description": (
            "Read the local Markdown runbook for a specific Kubernetes error type "
            "(CrashLoopBackOff, OOMKilled, ImagePullBackoff). "
            "Call this first whenever you identify an error type — it gives you "
            "structured, operator-approved remediation steps to ground your answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "error_type": {
                    "type": "string",
                    "description": "Kubernetes error type, e.g. CrashLoopBackOff, OOMKilled, ImagePullBackoff.",
                }
            },
            "required": ["error_type"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web via Tavily for up-to-date information about a Kubernetes issue. "
            "Use when the local runbook is insufficient, when the error looks like a known "
            "upstream bug, or when you need version-specific guidance. "
            "Pass a precise query such as 'Kubernetes OOMKilled JVM cgroup limits fix'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to send to Tavily.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_cluster_state",
        "description": (
            "Retrieve the current state of a pod as reported by 'kubectl describe pod'. "
            "Includes resource limits, last termination reason, restart count, and the "
            "Events section. Call this to confirm what Kubernetes observed about the pod."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pod_name": {
                    "type": "string",
                    "description": "Name of the Kubernetes pod to describe.",
                }
            },
            "required": ["pod_name"],
        },
    },
    {
        "name": "get_recent_logs",
        "description": (
            "Fetch the most recent log lines from a pod (equivalent to 'kubectl logs --tail=50'). "
            "Use this to read application-level error messages, stack traces, or OOM signals "
            "that complement the cluster state from get_cluster_state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pod_name": {
                    "type": "string",
                    "description": "Name of the Kubernetes pod whose logs to retrieve.",
                }
            },
            "required": ["pod_name"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a Kubernetes SRE assistant. Your job is to diagnose a pod error and produce a \
structured remediation report.

You have four tools:
• get_troubleshooting_docs  — consult the local runbook for a known error type
• search_web                — search the internet for edge cases or upstream bugs
• get_cluster_state         — read kubectl describe output for the affected pod
• get_recent_logs           — read recent application log lines for the affected pod

Workflow (follow this exactly):
1. Parse the error log to identify the error type and the pod name.
2. Call get_cluster_state and get_recent_logs for the pod (can be parallel).
3. Call get_troubleshooting_docs for the identified error type.
4. If the above does not fully explain the issue, call search_web for additional context.
5. Synthesise all tool results into a final answer.
6. Reply with ONLY a JSON object — no markdown fences, no extra text — with these keys:
   - "summary": one sentence describing the root cause in plain English
   - "confidence_score": integer 0–100 reflecting your diagnostic confidence
   - "action_items": list of concrete remediation strings (most impactful first)

Example final response:
{"summary": "Pod is OOMKilled because its 256 Mi memory limit is too low for the cache warm-up.", \
"confidence_score": 94, \
"action_items": ["Increase resources.limits.memory to at least 512Mi.", \
"Add -XX:MaxRAMPercentage=75.0 to cap JVM heap."]}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_pod_name(error_log: str) -> str:
    """
    Try to extract a pod name from the error log.

    Looks for common patterns such as:
      pod/my-pod-abc123
      pod: my-pod-abc123
      pod my-pod-abc123 in namespace
    Falls back to 'unknown-pod' if nothing is found.
    """
    patterns = [
        r"\bpod[/:\s]+([a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)",
        r"\b([a-z][a-z0-9\-]*-[a-z0-9]{5,10}-[a-z0-9]{5})\b",  # typical pod name suffix
    ]
    for pattern in patterns:
        match = re.search(pattern, error_log, re.IGNORECASE)
        if match:
            return match.group(1)
    return "unknown-pod"


def _dispatch(name: str, inputs: dict) -> str:
    dispatch_table = {
        "get_troubleshooting_docs": get_troubleshooting_docs,
        "search_web": search_web,
        "get_cluster_state": get_cluster_state,
        "get_recent_logs": get_recent_logs,
    }
    fn = dispatch_table.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return fn(**inputs)


# ---------------------------------------------------------------------------
# ReAct loop
# ---------------------------------------------------------------------------

def run_triage_agent(error_log: str) -> dict:
    """
    Run a ReAct-style triage loop using the Anthropic Messages API.

    The loop sends the error log, executes whatever tools Claude requests,
    and repeats until Claude returns a final JSON diagnosis.

    Returns a dict with keys:
      summary          (str)       — one-sentence root-cause description
      confidence_score (int)       — 0–100
      action_items     (list[str]) — concrete remediation steps
    """
    pod_name = _extract_pod_name(error_log)

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Pod name extracted from log: {pod_name}\n\n"
                f"Error log:\n\n{error_log}"
            ),
        }
    ]

    while True:
        with _anthropic.messages.stream(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=_SYSTEM,
            tools=_TOOLS,
            thinking={"type": "adaptive"},
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next(
                (block.text for block in response.content if block.type == "text"),
                "",
            )
            result = json.loads(text)
            return {
                "summary": str(result["summary"]),
                "confidence_score": int(result["confidence_score"]),
                "action_items": list(result["action_items"]),
            }

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = _dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason!r}")
