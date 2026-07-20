/**
 * Gerald — uConsole buddy adapter for GJC (Gajae Code) / pi.
 *
 * This is the GJC counterpart of the Claude Code hook scripts in
 * `bridge/bridge/hooks/`. It talks to the SAME bridge daemon over the SAME
 * unix-socket protocol (`bridge/bridge/protocol.py`), so the daemon and the
 * uConsole device need no changes — only the agent-facing layer differs.
 *
 * Event mapping (GJC → Gerald state):
 *   session_start          → thinking  ("session start")
 *   before_agent_start     → thinking  (prompt submitted)
 *   agent_start            → running
 *   tool_execution_start   → running   + appends a live feed line
 *   tool_execution_end     → error     (only when the tool failed)
 *   tool_call (bash)       → approval overlay → Y/N on device → allow/deny
 *   agent_end              → done       (decays to idle on the device)
 *   session_shutdown       → idle
 *   model_select           → HUD model name
 *
 * Install: symlink/copy into `~/.gjc/agent/extensions/` (see gjc/README.md),
 * or load ad-hoc with `gjc -e /path/to/uconsole-buddy.ts`.
 *
 * The type-only import below is erased at transpile time, so this file loads
 * unchanged under both `gjc` (@gajae-code/coding-agent) and `pi`
 * (@mariozechner/pi-coding-agent).
 */
import type { ExtensionAPI } from "@gajae-code/coding-agent";
import net from "node:net";
import os from "node:os";
import path from "node:path";

// --- Socket path (mirrors bridge/bridge/paths.py) ---------------------------
function expand(p: string): string {
	return p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p;
}
function socketPath(): string {
	const sock = process.env.UCONSOLE_BRIDGE_SOCK;
	if (sock) return expand(sock);
	const home = process.env.UCONSOLE_BRIDGE_HOME;
	const base = home ? expand(home) : path.join(os.homedir(), ".uconsole-buddy");
	return path.join(base, "run", "bridge.sock");
}

// Transport: prefer TCP ($UCONSOLE_BRIDGE_ADDR="host:port", e.g. a Tailscale
// address) for remote setups; otherwise the local unix socket.
const ADDR = process.env.UCONSOLE_BRIDGE_ADDR;
const SOCK = socketPath();

function connect(): net.Socket {
	if (ADDR) {
		const i = ADDR.lastIndexOf(":");
		const host = ADDR.slice(0, i) || "127.0.0.1";
		const port = Number(ADDR.slice(i + 1));
		return net.createConnection({ host, port });
	}
	return net.createConnection(SOCK);
}
const HINT_MAX = 120;
const FEED_MAX = 60;
const APPROVE_TIMEOUT_MS = 115_000;
const STATUS_TIMEOUT_MS = 3_000;
// Session identity for multi-session aggregation on the device (e.g. several
// tmux windows). sid is stable per gjc process; label is the project dir name.
const SID = String(process.pid);
const LABEL = (() => {
	try {
		return path.basename(process.cwd()) || os.hostname();
	} catch {
		return os.hostname();
	}
})();
// Which tools require a physical approval on the device. "bash" (default),
// "all", or "off". Mirrors Claude's PreToolUse(Bash) matcher.
const GATE = (process.env.UCONSOLE_BRIDGE_APPROVE ?? "bash").toLowerCase();
const LANG = (process.env.GERALD_LANG ?? "en").toLowerCase().startsWith("de") ? "de" : "en";

const MSG = {
	en: { sessionStart: "session start", thinking: "thinking", working: "working", done: "done" },
	de: { sessionStart: "session start", thinking: "denke nach", working: "arbeite", done: "fertig" },
}[LANG];

// --- Socket helpers ---------------------------------------------------------
/** Fire-and-forget status push; never rejects, never throws. */
function sendStatus(payload: Record<string, unknown>): Promise<void> {
	return new Promise((resolve) => {
		let done = false;
		const finish = () => {
			if (done) return;
			done = true;
			resolve();
		};
		let sock: net.Socket;
		try {
			sock = connect();
		} catch {
			finish();
			return;
		}
		sock.setTimeout(STATUS_TIMEOUT_MS);
		sock.on("connect", () => {
			sock.write(`${JSON.stringify({ type: "status", sid: SID, label: LABEL, ...payload })}\n`);
			sock.end();
		});
		sock.on("timeout", () => {
			sock.destroy();
			finish();
		});
		sock.on("error", finish);
		sock.on("close", finish);
	});
}

/** Round-trip approval request. Resolves "allow" | "deny" | "ask" (fail-safe "ask"). */
function requestApproval(id: string, tool: string, hint: string): Promise<"allow" | "deny" | "ask"> {
	return new Promise((resolve) => {
		let done = false;
		let buf = "";
		let sock: net.Socket;
		const finish = (decision: "allow" | "deny" | "ask") => {
			if (done) return;
			done = true;
			try {
				sock?.destroy();
			} catch {
				/* ignore */
			}
			resolve(decision);
		};
		try {
			sock = connect();
		} catch {
			finish("ask");
			return;
		}
		sock.setTimeout(APPROVE_TIMEOUT_MS);
		sock.on("connect", () => {
			sock.write(`${JSON.stringify({ type: "approve", id, tool, hint, sid: SID, label: LABEL })}\n`);
		});
		sock.on("data", (chunk) => {
			buf += chunk.toString("utf-8");
			const nl = buf.indexOf("\n");
			if (nl < 0) return;
			try {
				const msg = JSON.parse(buf.slice(0, nl));
				const d = msg?.decision;
				finish(d === "allow" || d === "deny" ? d : "ask");
			} catch {
				finish("ask");
			}
		});
		sock.on("timeout", () => finish("ask"));
		sock.on("error", () => finish("ask"));
		sock.on("close", () => finish("ask"));
	});
}

// --- Feed / hint formatting -------------------------------------------------
function toolHint(name: string, input: Record<string, unknown> | undefined): string {
	const ti = input ?? {};
	if (name === "bash") return String(ti.command ?? "");
	if (name === "read" || name === "write" || name === "edit") return path.basename(String(ti.path ?? ""));
	try {
		return JSON.stringify(ti);
	} catch {
		return "";
	}
}

function feedLine(name: string, input: Record<string, unknown> | undefined): string {
	const hhmm = new Date().toTimeString().slice(0, 5);
	const label = name.charAt(0).toUpperCase() + name.slice(1);
	return `${hhmm} ${label}: ${toolHint(name, input)}`.slice(0, FEED_MAX);
}

// --- Extension entrypoint ---------------------------------------------------
export default function (pi: ExtensionAPI): void {
	pi.on("session_start", () => {
		void sendStatus({ state: "thinking", msg: MSG.sessionStart });
	});

	pi.on("before_agent_start", () => {
		void sendStatus({ state: "thinking", msg: MSG.thinking });
	});

	pi.on("agent_start", () => {
		void sendStatus({ state: "running", msg: MSG.working });
	});

	pi.on("tool_execution_start", (event) => {
		void sendStatus({ state: "running", entry: feedLine(event.toolName, event.args) });
	});

	// Fills the previously-dead "error" state that no Claude hook ever emitted.
	pi.on("tool_execution_end", (event) => {
		if (event.isError) void sendStatus({ state: "error", msg: `${event.toolName} failed` });
	});

	pi.on("agent_end", () => {
		void sendStatus({ state: "done", msg: MSG.done });
	});

	pi.on("session_shutdown", () => {
		void sendStatus({ state: "idle", msg: "idle" });
	});

	pi.on("model_select", (event) => {
		const model = (event.model as { id?: string; name?: string } | undefined)?.id;
		if (model) void sendStatus({ hud: { model: String(model) } });
	});

	if (GATE !== "off") {
		pi.on("tool_call", async (event) => {
			if (GATE === "bash" && event.toolName !== "bash") return;
			const id = `${process.pid}#${event.toolCallId}`;
			const hint = toolHint(event.toolName, event.input as Record<string, unknown>).slice(0, HINT_MAX);
			const decision = await requestApproval(id, event.toolName, hint);
			if (decision === "deny") return { block: true, reason: "uConsole: deny" };
			// "allow" and fail-safe "ask" fall through to GJC's normal permission flow.
			return undefined;
		});
	}
}
