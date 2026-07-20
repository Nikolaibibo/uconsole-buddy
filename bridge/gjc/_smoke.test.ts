// Standalone smoke test for the GJC extension against a fake bridge daemon.
// Run: bun bridge/gjc/_smoke.test.ts
import net from "node:net";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const SOCK = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "ucb-")), "bridge.sock");
process.env.UCONSOLE_BRIDGE_SOCK = SOCK;

const received: any[] = [];
let approveDecision = "once"; // device says allow

const server = net.createServer((sock) => {
	let buf = "";
	sock.on("data", (c) => {
		buf += c.toString("utf-8");
		let nl: number;
		// biome-ignore lint/suspicious/noAssignInExpressions: loop drain
		while ((nl = buf.indexOf("\n")) >= 0) {
			const line = buf.slice(0, nl);
			buf = buf.slice(nl + 1);
			const msg = JSON.parse(line);
			received.push(msg);
			if (msg.type === "approve") {
				// daemon maps once->allow, deny->deny
				const decision = approveDecision === "once" ? "allow" : approveDecision === "deny" ? "deny" : "ask";
				sock.write(`${JSON.stringify({ decision })}\n`);
			} else {
				sock.write('{"decision":"ask"}\n');
			}
		}
	});
});

function listen(): Promise<void> {
	return new Promise((res) => server.listen(SOCK, () => res()));
}

// mock pi
type Handler = (e: any) => any;
const handlers = new Map<string, Handler>();
const pi = { on: (ev: string, h: Handler) => handlers.set(ev, h) };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

let failures = 0;
function assert(cond: boolean, label: string) {
	if (!cond) {
		failures++;
		console.error(`FAIL: ${label}`);
	} else {
		console.log(`ok:   ${label}`);
	}
}

async function main() {
	await listen();
	const mod = await import("./uconsole-buddy.ts");
	mod.default(pi as any);

	assert(handlers.has("session_start"), "subscribes session_start");
	assert(handlers.has("tool_call"), "subscribes tool_call (approval gate)");

	// fire status-style events
	await handlers.get("session_start")!({});
	await handlers.get("before_agent_start")!({ prompt: "hi" });
	await handlers.get("agent_start")!({});
	await handlers.get("tool_execution_start")!({ toolName: "edit", args: { path: "/a/b/c.ts" } });
	await handlers.get("tool_execution_end")!({ toolName: "bash", isError: true, result: {} });
	await handlers.get("agent_end")!({ messages: [] });
	await sleep(150);

	const states = received.filter((m) => m.type === "status").map((m) => m.state);
	assert(states.includes("thinking"), "emitted thinking");
	assert(states.includes("running"), "emitted running");
	assert(states.includes("error"), "emitted error on failed tool");
	assert(states.includes("done"), "emitted done");
	const feed = received.find((m) => m.entry);
	assert(!!feed && /Edit: c\.ts/.test(feed.entry), `feed line basename ok (${feed?.entry})`);

	// approval: allow (device 'once')
	received.length = 0;
	approveDecision = "once";
	const rAllow = await handlers.get("tool_call")!({ toolName: "bash", toolCallId: "t1", input: { command: "ls -la" } });
	assert(rAllow === undefined, "allow → not blocked");
	const appr = received.find((m) => m.type === "approve");
	assert(!!appr && appr.tool === "bash" && appr.hint === "ls -la", `approve payload ok (${appr?.hint})`);

	// approval: deny
	approveDecision = "deny";
	const rDeny = await handlers.get("tool_call")!({ toolName: "bash", toolCallId: "t2", input: { command: "rm -rf /" } });
	assert(!!rDeny && rDeny.block === true, "deny → block:true");

	// non-bash tool is not gated (default GATE=bash)
	const rRead = await handlers.get("tool_call")!({ toolName: "read", toolCallId: "t3", input: { path: "/x" } });
	assert(rRead === undefined, "read tool not gated by default");

	server.close();
	console.log(failures === 0 ? "\nALL PASS" : `\n${failures} FAILURE(S)`);
	process.exit(failures === 0 ? 0 : 1);
}

main();
