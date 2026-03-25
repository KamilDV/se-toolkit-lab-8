# Lab plan — Add Observability with VictoriaLogs and VictoriaTraces

**Topic:** structured logging, distributed tracing, and AI-assisted observability
**Date:** 2026-03-24

## Main goals

- Show students that unstructured text logs are nearly useless for debugging multi-service systems — structured logging makes the difference.
- Teach the two complementary views of a running system: logs tell you what happened at each service, traces tell you how a request flowed across services.
- Demonstrate that an AI agent becomes much more useful when it can access operational data — not just application data — through MCP tools.

<!-- sometimes, you can use a debugger. other times - no -->
<!-- fix a bug in a problematic endpoint (e.g. model field mismatch) -->
<!-- optional task - improve formatting of messages in clients -->
<!-- if not enough memory - use swap) -->

## Learning outcomes

By the end of this lab, students should be able to:

- [Understand] Explain how structured logs and distributed traces provide complementary views of a multi-service system — logs capture events, traces capture request flow.
- [Apply] Add structured JSON logging at key points across multiple services so that both successful and failed requests produce a defined sequence of queryable events.
- [Apply] Implement MCP tools that query the VictoriaLogs API and return meaningful summaries to the nanobot agent.
- [Apply] Implement MCP tools that query the VictoriaTraces API and return trace information to the nanobot agent.
- [Analyze] Verify that the AI agent can combine log and trace data to answer natural-language questions about system health under normal and failure conditions.
- [Create] Configure an AI agent with a skill prompt, a cron job, and a multi-step task that chains multiple tools to produce a periodic health report.

In simple words:

> 1. I can explain the difference between logs and traces and when to use each.
> 2. I can add structured logging across services so that every request produces a queryable trail of events.
> 3. I can build MCP tools that let the AI agent search and summarize logs.
> 4. I can build MCP tools that let the AI agent look up and interpret traces.
> 5. I can verify that the agent answers "what went wrong?" correctly when something breaks.
> 6. I can write a skill, configure a cron job, and set up a multi-step agent task that chains log and trace queries into a periodic health report.

## Lab story

The LMS has been running on your VM for weeks — backend, nanobot, Flutter web app, Caddy, PostgreSQL.
The team recently added VictoriaLogs, VictoriaTraces, and an OpenTelemetry Collector to the Docker Compose stack.
The backend is already instrumented with the OpenTelemetry SDK — traces flow into VictoriaTraces and logs are collected by VictoriaLogs — but the logs are still unstructured text, and nobody on the team knows how to use any of it.
When something goes wrong, nobody knows how to find the relevant traces or query the logs effectively.
Your team lead wants you to fix the logging, then wire both systems into the AI agent so anyone can ask about system health in plain language.

A senior engineer explains the assignment:

> 1. Add structured JSON logging across the backend and nanobot so every request — successful or failed — produces a defined sequence of queryable events.
> 2. Extend the nanobot agent with MCP tools that query VictoriaLogs, so users can ask about errors and request history.
> 3. Extend the nanobot agent with MCP tools that query VictoriaTraces, so users can ask about request flow and performance.
> 4. Write an observability skill, configure a cron job for periodic health checks, and verify the agent chains multiple tools in a multi-step investigation.

## Required tasks

### Task 1 — Add Structured Logging and Explore Traces

**Purpose:**

Structured logs with consistent fields turn free-text search into precise, filterable queries.
Traces show how a single request flows across services.
Understanding both data sources directly is a prerequisite for wiring them into the AI agent.

**Summary:**

#### Part A — Add structured logging

Students run `docker compose logs backend` and see unstructured text: Uvicorn startup messages, raw request lines, Python tracebacks.
They try to find "all errors from the backend" in this output and discover it requires fragile text matching.

Students then configure structured JSON logging across the backend and nanobot services.
They set up a JSON log formatter (via Python's logging or a library like `structlog`) so every entry has consistent fields: `level`, `event`, and `service`.

Next, students add log statements so that a single user request produces a defined sequence of events across services.
The task specifies the expected log sequence for two scenarios: a successful request and a failed request (database down).

**Expected log sequence — happy path** (e.g., user asks "what labs are available?"):

| #   | service | event                 | key fields                                |
| --- | ------- | --------------------- | ----------------------------------------- |
| 1   | nanobot | `ws_message_received` | `chat_id`                                 |
| 2   | nanobot | `tool_call`           | `tool`                                    |
| 3   | backend | `request_started`     | `method`, `path`                          |
| 4   | backend | `auth_success`        |                                           |
| 5   | backend | `db_query`            | `table`, `operation`                      |
| 6   | backend | `request_completed`   | `method`, `path`, `status`, `duration_ms` |
| 7   | nanobot | `tool_result`         | `tool`, `success`                         |
| 8   | nanobot | `ws_message_sent`     | `chat_id`                                 |

**Expected log sequence — error path** (database is down):

| #   | service | event                 | key fields                                     |
| --- | ------- | --------------------- | ---------------------------------------------- |
| 1   | nanobot | `ws_message_received` | `chat_id`                                      |
| 2   | nanobot | `tool_call`           | `tool`                                         |
| 3   | backend | `request_started`     | `method`, `path`                               |
| 4   | backend | `auth_success`        |                                                |
| 5   | backend | `db_query`            | `level: "error"`, `table`, `error`             |
| 6   | backend | `request_completed`   | `method`, `path`, `status: 500`, `duration_ms` |
| 7   | nanobot | `tool_result`         | `tool`, `success: false`                       |
| 8   | nanobot | `ws_message_sent`     | `chat_id`                                      |

Students also add an `auth_failure` event (with `level: "warning"`) for requests with an invalid API key.

Students figure out where in the code each log statement belongs — in the webchat channel (`nanobot_webchat`), the MCP tool server (`lms_mcp`), and the backend (middleware, routes, DB layer).
After redeploying, they trigger both scenarios and verify the full sequences appear in `docker compose logs`.

#### Part B — Explore logs in VictoriaLogs

Students open the VictoriaLogs web UI (vmui) and discover that the same structured logs are queryable with LogsQL — filtering by `service`, `level`, `event`, and time range.
They run the same queries they struggled with in Part A and see how structured fields make them trivial.

Students also use provided `poe` tasks to query VictoriaLogs from the terminal — e.g., `uv run poe logs-search "error"` to search by keyword and `uv run poe logs-count` to count errors per service over a time window.

#### Part C — Explore traces in VictoriaTraces

Students open the VictoriaTraces UI and trigger a request through the Flutter web app.
They find the resulting trace, inspect the span hierarchy, and identify which service each span belongs to.
They then trigger a failure (e.g., stop PostgreSQL) and compare the healthy and error traces — noting where the error appears and how the trace duration changes.

Students also use provided `poe` tasks to query the VictoriaTraces HTTP API (Jaeger-compatible endpoints) — e.g., `uv run poe traces-list` to list recent traces for a service and `uv run poe trace-get <trace-id>` to fetch a specific trace by ID.

**Acceptance criteria:**

- Both services emit JSON-structured log entries with at least `level`, `event`, and `service` fields.
- A successful request produces the happy-path log sequence, visible in `docker compose logs`.
- A failed request (database down) produces the error-path log sequence, with `level: "error"` on the DB query event.
- A request with an invalid API key produces an `auth_failure` event with `level: "warning"`.
- The student can query structured logs in VictoriaLogs by `service`, `level`, and `event` fields.
- The student can use `poe` tasks to search logs and count errors from the terminal.
- The student can find a trace in the VictoriaTraces UI and identify the span hierarchy for a cross-service request.
- The student can use `poe` tasks to list recent traces and fetch a trace by ID.

---

### Task 2 — Add Observability MCP Tools to the Nanobot Agent

**Purpose:**

Connecting the AI agent to VictoriaLogs and VictoriaTraces lets users ask about errors, request flow, and system health in natural language instead of writing queries by hand.

**Summary:**

#### Part A — Log query tools

Students add MCP tools to the nanobot's MCP server that query the VictoriaLogs HTTP API.
They implement at least two tools: one that searches logs by keyword and time range (returning recent matching entries), and one that counts errors per service over a time window (returning a summary).
Each tool constructs a LogsQL query, sends it to the VictoriaLogs query endpoint, parses the JSON response, and returns a structured result.

After redeploying the nanobot, students verify the tools work under both normal and failure conditions.
They ask the agent about errors when the system is healthy (expecting "no errors found" or similar) and after triggering a failure (expecting a summary mentioning the affected service and error).

#### Part B — Trace query tools

Students implement at least two tools that query the VictoriaTraces HTTP API (Jaeger-compatible query endpoints): one that lists recent traces for a service (with duration and status), and one that fetches a specific trace by ID (returning the span hierarchy).
Each tool queries the VictoriaTraces API, parses the response, and returns a structured summary.

After redeploying the nanobot, students verify the tools work by asking the agent trace-related questions through the Flutter web app.
They test fetching recent traces and looking up a specific trace by ID.

**Acceptance criteria:**

- At least two MCP tools for querying VictoriaLogs are registered in the MCP server.
- The agent answers "any errors in the last hour?" correctly under normal conditions.
- The agent answers "any errors in the last hour?" correctly after a failure, mentioning the affected service.
- At least two MCP tools for querying VictoriaTraces are registered in the MCP server.
- The agent answers a question about recent request performance by calling the trace tools.
- The agent can fetch and summarize a specific trace by ID.
- The MCP server starts without errors after the changes.

---

### Task 3 — Write a Skill and Configure a Cron Health Check

**Purpose:**

A skill prompt teaches the agent *when* and *how* to use its tools; a cron job makes the agent proactive instead of reactive; a multi-step task shows that the agent can chain tools autonomously.

**Summary:**

Students create a new observability skill file (`workspace/skills/observability/SKILL.md`).
The skill teaches the agent about its log and trace tools: what each tool does, when to use it, and how to combine them.
For example, the skill should instruct the agent that when asked "what went wrong?", it should first search logs for recent errors, extract a trace ID from the results, then fetch the full trace to show the request flow.
Students also add guidance for summarizing results concisely rather than dumping raw data.

Next, students configure a cron job in `cron/jobs.json` that runs a periodic health check.
The job uses the `agent_turn` payload kind — it sends a message like "Check for errors in the last 15 minutes and report a summary" to the agent on a schedule (e.g., every 15 minutes).
The agent receives this as a regular message, reasons using the observability skill, calls the log and trace MCP tools, and delivers the result to the webchat channel.

Students verify the cron job fires by setting a short interval (e.g., every 2 minutes), waiting for a cycle, and checking that the agent produced a health report in the Flutter web app.
They also test the multi-step scenario: trigger a failure, wait for the next cron cycle, and verify the agent's report mentions the errors and includes trace information.

**Acceptance criteria:**

- An observability skill file exists at `workspace/skills/observability/SKILL.md` and is loaded by the agent.
- The skill guides the agent to chain log and trace tools for multi-step investigations.
- A cron job is configured in `cron/jobs.json` that triggers a periodic health check via `agent_turn`.
- The cron job fires on schedule and the agent delivers a health report to the webchat channel.
- When errors exist, the health report includes information from both log and trace tools.

---

## Optional task

### Task 1 — Set Up Error Alerting

**Purpose:**

Detecting problems before users report them is the difference between proactive and reactive operations.

**Summary:**

Students configure an alerting pipeline that fires when the error rate crosses a threshold.
They add vmalert (part of the VictoriaMetrics stack) as a Docker Compose service with a LogsQL-based alerting rule — for example, trigger when more than five log entries matching `level: "error"` appear within a 5-minute window.

Fired alerts are visible in the vmalert UI and queryable via its API.
Students add an MCP tool to the nanobot agent that checks vmalert's `/api/v1/alerts` endpoint and reports active alerts.
This way, a user can ask the agent "are there any active alerts?" and get a real answer — closing the loop between observability and the AI assistant.

To verify, students trigger the alert by stopping PostgreSQL and sending several requests, then confirm the alert appears in the vmalert UI and the nanobot agent reports it when asked.

**Acceptance criteria:**

- vmalert is running as a Docker Compose service with at least one LogsQL-based alerting rule.
- The alert fires when the error threshold is exceeded within the configured time window.
- An MCP tool reports active alerts from the vmalert API to the nanobot agent.
- The alerting rule and threshold are configurable without code changes.
