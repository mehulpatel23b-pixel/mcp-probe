# mcp-probe

**Zero-dependency smoke-tester for MCP (Model Context Protocol) stdio servers.**
Handshake check, tool listing, and one safe call per tool with auto-synthesized arguments — plus CI-friendly exit codes. Pure Python standard library, no Node, no SDKs, no framework.

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-00C853?style=flat-square)](https://github.com/mehulpatel23b-pixel/mcp-probe/blob/main/requirements.txt)
[![MIT license](https://img.shields.io/badge/license-MIT-000000?style=flat-square)](https://github.com/mehulpatel23b-pixel/mcp-probe/blob/main/LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-6E4C9E?style=flat-square)](https://modelcontextprotocol.io)
![Tests](https://img.shields.io/badge/tests-20%20passing-00C853?style=flat-square)
![Python versions](https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat-square)

`mcp-probe` launches any MCP stdio server as a subprocess, drives the real MCP handshake (`initialize` → `notifications/initialized`), lists every advertised tool (following pagination cursors), and then calls **each tool once** with minimal dummy arguments synthesized from its own JSON Schema. The result: a one-command answer to *"does my MCP server actually start, speak the protocol, and respond when a tool is invoked — from the outside, exactly like an MCP client would see it?"*

It is the missing `curl` for the MCP ecosystem: instead of wiring a server into Claude Desktop / Cursor / an agent runtime to find out it is broken, you get a deterministic, scriptable verdict in under a second.

---

## Table of contents

- [Why](#why)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Usage](#usage)
  - [Command reference](#command-reference)
  - [Exit codes (CI policy)](#exit-codes-ci-policy)
  - [Sample output](#sample-output)
- [How synthesized arguments work](#how-synthesized-arguments-work)
- [Architecture overview](#architecture-overview)
- [Project structure](#project-structure)
- [Running the tests](#running-the-tests)
- [Real-world use cases](#real-world-use-cases)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)

---

## Why

The MCP ecosystem has exploded: every AI IDE, agent framework, and assistant platform now speaks the Model Context Protocol, and thousands of community MCP servers ship every month. The day-to-day pain is remarkably consistent:

- **Wiring-first debugging.** The official route for "does my server work?" is to register it in Claude Desktop, Cursor, or a client SDK and squint at logs. Feedback loop: minutes. With mcp-probe: one shell command.
- **Broken tools that break silently.** A server can advertise ten tools and have nine of them crash on the very first call (missing env var, wrong path schema, unhandled exception). Listing tools is not enough — mcp-probe *calls* each one and separates "answered with a handled error" from "crashed / hung."
- **No CI gate before publishing.** If you publish MCP servers (to a registry, a marketplace, or just a README install line), regressions in the protocol layer reach users. mcp-probe runs in any CI pipeline with zero dependencies and gives you a machine-readable verdict (`--format json`) and exit-code policy you can enforce.
- **Heavyweight alternatives.** The reference inspector is a Node application with a full web UI — great for interactive exploration, wrong for a smoke test in a pipeline or a container healthcheck.

mcp-probe is deliberately the opposite: single-purpose, pure stdlib, ~100% testable, exit-code-driven.

---

## Installation

**Requirements:** Python 3.9+ (standard library only). No `pip install` of anything else.

### Option A — run straight from a clone (recommended)

```bash
git clone https://github.com/mehulpatel23b-pixel/mcp-probe.git
cd mcp-probe
PYTHONPATH=src python3 -m mcp_probe.cli --help
```

### Option B — install into an environment

```bash
cd mcp-probe
pip install .          # installs the `mcp-probe` console command
mcp-probe --help
```

`pip install -e .` works too for development. The `requirements.txt` file is intentionally empty — mcp-probe has **zero runtime dependencies**, so it slots into any CI image that has Python, with no supply-chain additions.

### Verify the install

```bash
mcp-probe --version
# mcp-probe 1.0.0
```

---

## Quick start

Probe a real community server (needs Node for this particular one, but any stdio server works):

```bash
# Filesystem server — the canonical first example
mcp-probe -- npx -y @modelcontextprotocol/server-filesystem /tmp

# Or a Python-based server
mcp-probe -- uvx mcp-server-fetch

# Or one you are developing locally
mcp-probe -- python my_server.py
```

Output (abbreviated):

```
mcp-probe report
  command     : npx -y @modelcontextprotocol/server-filesystem /tmp
  server      : github/mcp-filesystem v1.2.1
  protocol    : 2025-06-18
  handshake   : OK
  tools found : 11

  status        ms  tool
  ------- --------  ----------------------------------
  [ok]           7  read_file  (required: path)
           output: mcp-probe
  [ok]           4  list_directory  (required: path)
           output: mcp-probe
  ...
```

Every tool that answered got *called*, not just listed. The `[ok]` badge means a full round trip: request → server → valid JSON-RPC response.

---

## Usage

The server command always comes **after `--`** so mcp-probe never misparses your server's own flags.

```bash
mcp-probe [OPTIONS] -- SERVER COMMAND [SERVER ARGS...]
```

You may also pass the command as a single quoted string: `mcp-probe "uvx mcp-server-fetch"`.

### Command reference

| Flag | Meaning |
|---|---|
| `--list-only` | Handshake + list tools; never call them (server inventory mode) |
| `--no-calls` | Alias of `--list-only` |
| `--tool NAME` | Probe only the named tool; repeatable (`--tool a --tool b`) |
| `--fail-on-tool-error` | Treat `isError=true` replies as CI failures (exit 1) |
| `--format text\|json` | Human table (default) or machine-readable JSON report |
| `--connect-timeout N` | Seconds to wait for handshake/listing (default 20) |
| `--call-timeout N` | Seconds to wait per tool call (default 30) |
| `--cwd DIR` | Working directory for the server subprocess |
| `--version`, `--help` | Standard |

### Exit codes (CI policy)

mcp-probe separates *protocol health* from *business-logic answers*, which is what makes it usable as a CI gate:

| Code | Meaning |
|---|---|
| `0` | Handshake OK, listing OK, every probed tool answered a round trip (handled `isError` replies count as answered) |
| `1` | Protocol worked but something answered badly: a tool **timed out**, returned an **RPC error**, or **killed the connection** — or `--fail-on-tool-error` was set and a tool replied `isError=true` |
| `2` | Fatal: server failed to start, handshake failed, non-JSON output, or a requested `--tool` was never advertised |

The distinction matters: a tool legitimately rejecting dummy arguments (`[ERR]`) is usually *fine* — it proves the tool is wired. What you must catch in CI is `[TMO]`, `[RPC]`, and `[DEAD]`.

### Sample output

Full probe of the bundled test fixture (`tests/fake_server.py`, included in the repo):

```bash
mcp-probe -- python3 tests/fake_server.py
```

```
mcp-probe report
  command     : python3 tests/fake_server.py
  server      : fake-mcp v0.9.0
  protocol    : 2025-06-18
  handshake   : OK
  tools found : 3

  status        ms  tool
  ------- --------  ----------------------------------
  [ok]           0  echo  (required: text)
           output: mcp-probe
  [ok]           0  add  (required: a, b)
           output: 0
  [ERR]          0  explode  (required: -)
           output: kaboom: bad input

exit code: 0
```

JSON mode (trimmed) for pipelines and dashboards:

```json
{
  "serverCommand": ["python3", "tests/fake_server.py"],
  "ok": true,
  "fatalError": null,
  "serverInfo": { "name": "fake-mcp", "version": "0.9.0" },
  "protocolVersion": "2025-06-18",
  "toolCount": 3,
  "tools": [
    {
      "name": "echo",
      "description": "Echo the given text back.",
      "required": ["text"],
      "synthesizedArguments": { "text": "mcp-probe" },
      "status": "ok",
      "durationMs": 0.1,
      "output": "mcp-probe"
    }
  ]
}
```

And what failure looks like — a server that speaks garbage instead of JSON-RPC:

```
mcp-probe report
  command     : python3 -c ...
  server      : ? v?
  handshake   : FAILED
  fatal error : server sent non-JSON line: 'garbage'
exit code: 2
```

---

## How synthesized arguments work

The smoke call is only useful if it is **safe** and **automatic**. mcp-probe reads each tool's `inputSchema` and builds a minimal argument object for exactly the `required` properties, using inert zero-values:

| Schema type | Synthetic value |
|---|---|
| `string` | `"mcp-probe"` (sentinel — never a path, URL, or command) |
| `integer` / `number` | `0` |
| `boolean` | `false` |
| `array` | `[]` |
| `object` | `{}` |
| `null` | `null` |
| unknown / missing | `"mcp-probe"` |

Design guarantees:

- **Optional properties are omitted entirely** — nothing is invented that the schema did not demand.
- **No side effects by construction:** empty collections, zero, false, and a non-path sentinel string are chosen precisely because they are the least dangerous values expressible in JSON.
- **A handled rejection is a pass.** Tools with real validation (`isError=true` on `"mcp-probe"`) return `[ERR]` and exit 0 — the point is proving the tool is *reachable and responsive*, not that dummy input performs real work.

If you want a controlled real invocation instead, use `--tool NAME` against a tool whose required arguments are trivial, or wire a real MCP client for functional testing. mcp-probe is the smoke layer beneath that.

---

## Architecture overview

```
            ┌────────────────────────────────────────────────┐
            │                     CLI                          │
            │  argparse → options → exit-code policy → stdout │
            └───────────────────────┬────────────────────────┘
                                    │ report dict
            ┌───────────────────────┴────────────────┐
            │                 PROBE                    │
            │  orchestration, per-tool states,       │
            │  timing, fatal-error capture            │
            └───────┬──────────────────┬──────────────┘
                    │                  │
        ┌───────────┴───────┐   ┌──────┴───────────────┐
        │     SYNTHESIZE    │   │       CLIENT         │
        │  JSON Schema →    │   │  JSON-RPC 2.0 over   │
        │  safe dummy args   │   │  stdio (select-based │
        └───────────────┬───┘   │  timeouts)           │
                        │       └──────────┬───────────┘
                        └──── arguments ───┘
                                        │ spawn + pipes
                                 ┌──────┴───────┐
                                 │  MCP SERVER  │
                                 │ (any stdio)   │
                                 └──────────────┘
```

Flow of a probe run:

1. **Spawn** — the server command starts as a subprocess with piped stdin/stdout/stderr (`client.StdioMCPClient`).
2. **Handshake** — MCP `initialize` request with protocol `2025-06-18`; the negotiated `protocolVersion` and `serverInfo` are captured; `notifications/initialized` is sent. Handshake failure is fatal and captures the server's stderr tail for the report.
3. **Enumerate** — `tools/list` is called repeatedly following `nextCursor` until every tool is collected (duplicates are guarded by name).
4. **Smoke-call** — for each tool, `synthesize.synthesize_arguments` builds args from the schema, `tools/call` is issued with its own timeout, and one of five statuses is recorded: `ok`, `tool-error`, `rpc-error`, `timeout`, `unreachable`, each with millisecond timing and output excerpt.
5. **Report** — `report.render_text` / `report.render_json` produce output; `probe.probe_exit_code` translates the run into 0/1/2 for the shell.

The wire layer is belt-and-braces by design: strict JSON-RPC id matching, per-frame JSON validation with a protocol error on garbage, `select`-based timeouts (never a hung CI job), EOF detection with the server exit code and stderr tail, and pagination cursor handling.

---

## Project structure

```
mcp-probe/
├── src/
│   └── mcp_probe/
│       ├── __init__.py      # version metadata
│       ├── cli.py           # argparse entrypoint, exit-code policy
│       ├── client.py        # minimal MCP stdio client (JSON-RPC 2.0)
│       ├── errors.py        # typed exception hierarchy
│       ├── probe.py         # orchestration + result model
│       ├── report.py        # text / JSON renderers
│       └── synthesize.py    # JSON Schema → safe dummy arguments
├── tests/
│   ├── fake_server.py      # bundled MCP-like fixture server (3 tools)
│   ├── test_client.py      # handshake, listing, calls, error paths
│   ├── test_probe.py       # end-to-end probe scenarios + exit policy
│   └── test_synthesize.py  # schema-to-arguments rules
├── .gitignore
├── LICENSE                 # MIT
├── pyproject.toml          # packaging + `mcp-probe` console script
├── README.md
└── requirements.txt        # empty on purpose: zero dependencies
```

---

## Running the tests

```bash
git clone https://github.com/mehulpatel23b-pixel/mcp-probe.git
cd mcp-probe
python3 -m unittest discover -s tests -v
```

```
test_boolean_and_array_and_object ... ok
test_call_tool_happy_path ... ok
test_call_tool_iserror_is_a_result_not_exception ... ok
...
Ran 20 tests in 2.7s

OK
```

The suite exercises the real subprocess → pipes → JSON-RPC path via the bundled fixture server, including timeout handling, dead processes, non-JSON output, tool filtering, and the full exit-code policy. No network, no mocks of the transport — everything is a real round trip.

---

## Real-world use cases

1. **Pre-publish CI gate for MCP server repos.** Add one step to GitHub Actions and every push *actually boots the server and invokes all its tools* before release:
   ```yaml
   - run: |
       PYTHONPATH=src python3 -m mcp_probe.cli \
         --fail-on-tool-error --format json \
         -- python src/my_server.py
   ```
2. **Registry/marketplace acceptance testing.** If you run a directory of community MCP servers, mcp-probe is a cheap, uniform first-pass health check before deeper functional review: dead links and missing env vars announce themselves in the handshake or smoke calls.
3. **"Why won't Claude/Cursor see my tools?"** The fastest possible differential: if mcp-probe handshakes and lists tools cleanly but your client shows nothing, the problem is your client configuration — not the server. If mcp-probe fails too, the report's `stderrTail` already found the server-side exception for you.
4. **Local dev watch.** Combine with `entr`/`watchexec` to re-probe on every file save during development — sub-second feedback instead of reload-the-client-again loops.
5. **Container/orchestration healthchecks.** Because it is pure stdlib, the probe can live in a `curl -f`-style healthcheck or a Kubernetes readiness probe wrapper for server deployments, flagging servers that are up but no longer answering the protocol.
6. **Comparative smoke reports.** `--format json` output is stable and diffable — snapshot it in CI and get an automatic delta review whenever a release adds, removes, or breaks a tool.
7. **Security review of third-party servers.** Before wiring an unknown community server into an agent runtime with your credentials, `--list-only` gives you the exact tool inventory and required parameters in one shot — an inventory-first step before granting anything.

---

## Limitations

- **stdio transport only** (where the vast majority of local dev servers live). HTTP/SSE transports are out of scope for v1.
- **Smoke, not functional testing** — synthesized arguments prove reachability and protocol correctness, not business correctness. Pair with real fixtures for the latter.
- Tools guarded by access codes and auth flows return `[ERR]`/`[RPC]` by design — use `--list-only` for inventory in that scenario.
- The MCP spec is evolving; `initialize` negotiates with the server and the negotiated version is reported. Tool result shapes follow the MCP content-block convention.

---

## Contributing

Issues and PRs are welcome — especially for spec-version compatibility tables and additional fixture servers. Please keep the zero-dependency invariant: everything must run on the Python standard library, and every change must keep the test suite green:

```bash
python3 -m unittest discover -s tests
```

---

## License

[MIT](LICENSE) © Mehul Patel. The Model Context Protocol is maintained by its own community; this project is an independent testing utility with no affiliation.
