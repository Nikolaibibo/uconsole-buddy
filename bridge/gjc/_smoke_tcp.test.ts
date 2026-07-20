// Smoke test for the extension's TCP transport ($UCONSOLE_BRIDGE_ADDR).
// Run: bun bridge/gjc/_smoke_tcp.test.ts
import net from "node:net";

const received: any[] = [];
const server = net.createServer((sock) => {
	let buf = "";
	sock.on("data", (c) => {
		buf += c.toString("utf-8");
		let nl: number;
		// biome-ignore lint/suspicious/noAssignInExpressions: drain loop
		while ((nl = buf.indexOf("\n")) >= 0) {
			const line = buf.slice(0, nl);
			buf = buf.slice(nl + 1);
			const msg = JSON.parse(line);
			received.push(msg);
			sock.write(msg.type === "approve" ? '{"decision":"deny"}\n' : '{"decision":"ask"}\n');
		}
	});
});

let failures = 0;
const assert = (c: boolean, l: string) => {
	console.log((c ? "ok:   " : "FAIL: ") + l);
	if (!c) failures++;
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function main() {
	await new Promise<void>((res) => server.listen(0, "127.0.0.1", () => res()));
	const port = (server.address() as net.AddressInfo).port;
	process.env.UCONSOLE_BRIDGE_ADDR = `127.0.0.1:${port}`;
	delete process.env.UCONSOLE_BRIDGE_SOCK;

	const handlers = new Map<string, (e: any) => any>();
	const pi = { on: (ev: string, h: (e: any) => any) => handlers.set(ev, h) };
	const mod = await import("./uconsole-buddy.ts");
	mod.default(pi as any);

	await handlers.get("agent_start")!({});
	await sleep(100);
	assert(received.some((m) => m.type === "status" && m.state === "running"), "status over TCP received");

	const r = await handlers.get("tool_call")!({ toolName: "bash", toolCallId: "x1", input: { command: "rm -rf /" } });
	assert(!!r && r.block === true, "TCP approval deny -> block:true");
	assert(received.some((m) => m.type === "approve" && m.hint === "rm -rf /"), "approve payload over TCP");

	server.close();
	console.log("\n" + (failures === 0 ? "ALL PASS" : `${failures} FAILURE(S)`));
	process.exit(failures === 0 ? 0 : 1);
}
main();
