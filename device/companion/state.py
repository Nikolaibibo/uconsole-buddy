"""App-State + Prompt-State-Machine. Reine Logik; Zeit wird als `now` (float s) injiziert."""

TIMEOUT_S = 30.0  # kein Snapshot länger → disconnected


class AppState:
    def __init__(self) -> None:
        self.total = 0
        self.running = 0
        self.waiting = 0
        self.msg = ""
        self.entries: list[str] = []
        self.tokens = 0
        self.tokens_today = 0
        self.prompt: dict | None = None
        self.hud: dict | None = None
        self.owner = ""
        self.name = "Claude-uConsole"
        self.appr = 0
        self.deny = 0
        self.connected = False
        self.secure = False
        self.claude_state = ""
        # interne State-Machine
        self._last_prompt_id = ""
        self._response_sent = False
        self._prompt_arrived = 0.0
        self._decision_sent = 0.0
        self._last_snapshot: float | None = None

    def apply_snapshot(self, msg: dict, now: float) -> None:
        self.total = msg.get("total", 0)
        self.running = msg.get("running", 0)
        self.waiting = msg.get("waiting", 0)
        self.msg = msg.get("msg", "")
        self.entries = msg.get("entries", [])
        self.tokens = msg.get("tokens", self.tokens)
        self.tokens_today = msg.get("tokens_today", self.tokens_today)
        self.prompt = msg.get("prompt")  # dict oder None
        new_hud = msg.get("hud")
        if new_hud:
            self.hud = new_hud
        self.claude_state = msg.get("state", "")
        new_id = self.prompt["id"] if self.prompt else ""
        if new_id != self._last_prompt_id:
            self._last_prompt_id = new_id
            self._response_sent = False
            if new_id:
                self._prompt_arrived = now
        self._last_snapshot = now

    def record_decision(self, decision: str, now: float) -> None:
        self._response_sent = True
        self._decision_sent = now
        if decision == "once":
            self.appr += 1
        elif decision == "deny":
            self.deny += 1

    def in_prompt(self) -> bool:
        return bool(self.prompt) and not self._response_sent

    def should_rearm(self, now: float, timeout: float = 4.0) -> bool:
        return (self._response_sent and bool(self.prompt)
                and (now - self._decision_sent) > timeout)

    def rearm(self) -> None:
        self._response_sent = False

    def connection_state(self, now: float) -> str:
        if self._last_snapshot is None or (now - self._last_snapshot) > TIMEOUT_S:
            return "disconnected"
        if self.prompt:
            return "waiting"
        if self.running > 0:
            return "running"
        return "idle"

    def mood_state(self, now: float) -> str:
        return self.claude_state or self.connection_state(now)

    def set_owner(self, name: str) -> None:
        self.owner = name

    def set_name(self, name: str) -> None:
        self.name = name

    def prompt_id(self) -> str:
        return self.prompt["id"] if self.prompt else ""
