import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createConnection } from "node:net";
import { join } from "node:path";

/** Speaks only the final assistant answer after an agent run settles. */
export default function speakFinal(pi: ExtensionAPI) {
  let enabled = true;
  let finalText = "";
  let queue: string[] = [];
  let speaking = false;
  let socketPath = "";
  let interactive = false;

  const maxChunkChars = 280;

  function clean(text: string): string {
    return text
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/<https?:\/\/[^>]+>/g, " ")
      .replace(/https?:\/\/\S+/g, " ")
      .replace(/^\s{0,3}(?:#{1,6}|[-+*]|\d+[.)])\s*/gm, "")
      .replace(/[*_~>|]/g, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function chunks(text: string): string[] {
    const result: string[] = [];
    let current = "";

    for (let unit of text.split(/(?<=[.!?])\s+/)) {
      unit = unit.trim();
      while (unit.length > maxChunkChars) {
        let splitAt = unit.lastIndexOf(" ", maxChunkChars);
        if (splitAt < 1) splitAt = maxChunkChars;
        if (current) result.push(current);
        result.push(unit.slice(0, splitAt).trim());
        current = "";
        unit = unit.slice(splitAt).trim();
      }
      if (!unit) continue;
      const candidate = `${current} ${unit}`.trim();
      if (current && candidate.length > maxChunkChars) {
        result.push(current);
        current = unit;
      } else {
        current = candidate;
      }
    }

    if (current) result.push(current);
    return result;
  }

  function send(text: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = createConnection(socketPath);
      let response = "";
      socket.setEncoding("utf8");
      socket.setTimeout(120_000);
      socket.once("connect", () => socket.end(text));
      socket.on("data", (chunk) => { response += chunk; });
      socket.once("end", () => {
        response.trim() === "OK"
          ? resolve()
          : reject(new Error(response.trim() || "empty speak response"));
      });
      socket.once("timeout", () => socket.destroy(new Error("speak socket timeout")));
      socket.once("error", reject);
    });
  }

  async function drain(): Promise<void> {
    if (speaking) return;
    speaking = true;
    try {
      while (enabled && queue.length > 0) {
        try {
          await send(queue.shift()!);
        } catch {
          queue = [];
          break;
        }
      }
    } finally {
      speaking = false;
    }
  }

  pi.on("session_start", (_event, ctx) => {
    socketPath = process.env.PI_SPEAK_SOCKET ?? join(ctx.cwd, "run", "clone.sock");
    interactive = ctx.mode === "tui";
    if (interactive) ctx.ui.setStatus("speak-final", enabled ? "🔊 final answer" : undefined);
  });

  pi.on("agent_start", () => {
    finalText = "";
  });

  pi.on("message_end", (event) => {
    if (event.message.role !== "assistant") return;
    finalText = event.message.content
      .filter((block): block is { type: "text"; text: string } => block.type === "text")
      .map((block) => block.text)
      .join("\n");
  });

  pi.on("agent_settled", () => {
    if (!enabled || !interactive) return;
    const text = clean(finalText);
    finalText = "";
    if (!text) return;
    queue.push(...chunks(text));
    void drain();
  });

  pi.on("session_shutdown", () => {
    enabled = false;
    queue = [];
  });

  pi.registerCommand("speak-stream", {
    description: "Toggle speech for final assistant answers",
    handler: async (_args, ctx) => {
      enabled = !enabled;
      if (!enabled) queue = [];
      ctx.ui.setStatus("speak-final", enabled ? "🔊 final answer" : undefined);
      ctx.ui.notify(`Final-answer speech ${enabled ? "on" : "off"}`, "info");
    },
  });
}
