/**
 * ra-guard — OpenCode adapter for the Research Paper Agent workspace guardrails.
 *
 * The guardrail logic lives in `scripts/ra/hooks.py` and is tool-agnostic: it reads a JSON
 * payload on stdin, prints a reason on stderr and exits 2 to block. Claude Code feeds it
 * through `.claude/settings.json`. This plugin is the same transport for OpenCode:
 *
 *   Claude Code                         OpenCode (this plugin)
 *   ----------------------------------  -------------------------------------------
 *   PreToolUse  Edit|Write|MultiEdit    ctx.tool.hook("execute.before")  tool = edit
 *   PreToolUse  Read|Glob|Grep          ctx.tool.hook("execute.before")  tool = read/glob/grep
 *   PreToolUse  Bash|PowerShell        ctx.tool.hook("execute.before")  tool = shell
 *   PreToolUse  Skill                   ctx.tool.hook("execute.before")  tool = skill
 *   PostToolUse Edit|Write|MultiEdit    ctx.tool.hook("execute.after")
 *   UserPromptSubmit                    ctx.session.hook("prompt")
 *   SessionStart                        ctx.session.hook("prompt") on the first prompt
 *   Stop                                ctx.tool.hook("execute.after")  (lock backstop)
 *
 * Nothing here re-implements a rule: every decision is taken by `ra hook <event>`, so the
 * Claude Code and OpenCode paths cannot drift apart. Failures are closed: if the guard cannot
 * be reached, the call is blocked rather than let through.
 *
 * PATHS. The guard runs under the workspace's own Python, which lives inside WSL2 (the
 * `.venv`, `ra` launcher and hook scripts are all Linux-side). It therefore needs POSIX
 * paths: `os.path.isabs("C:\\...")` is False under Linux, and a Windows path would be
 * mangled into a bogus "workspace root" path and denied. This plugin therefore converts
 * every path to its WSL form before handing it over. (This also means the workspace is
 * meant to be driven from inside WSL, e.g. Claude Code's Linux build.)
 *
 * Known deliberate gap: OpenCode's `patch` tool (multi-file unified diff, offered to some
 * GPT models) cannot be expressed in the payload shape `hooks.py` understands, so its content
 * checks cannot run. `patch` is therefore refused here; use `edit`/`write`, which are guarded.
 * The static path rules stay covered by the `permissions` block in `opencode.json`.
 */

import { Plugin } from "@opencode/plugin"
import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BLOCK = "[workspace guard] BLOCKED: "

// --------------------------------------------------------------------- workspace

function isWorkspace(dir: string): boolean {
  try {
    return existsSync(path.join(dir, "ra")) && existsSync(path.join(dir, "scripts", "cli.py"))
  } catch {
    return false
  }
}

function findWorkspace(): string | null {
  const seeds = [path.resolve(HERE, "..", "..", ".."), path.resolve(HERE, "..", ".."), process.cwd()]
  for (const seed of seeds) {
    let dir = path.resolve(seed)
    for (let i = 0; i < 12; i++) {
      if (isWorkspace(dir)) return dir
      const parent = path.dirname(dir)
      if (parent === dir) break
      dir = parent
    }
  }
  return null
}

// ------------------------------------------------------------------ hook runner

type Run = { code: number; stdout: string; stderr: string }

function run(ws: string, args: string[], payload?: unknown): Promise<Run> {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn("bash", args, {
        cwd: ws,
        // CLAUDECODE=1 marks an agent-invoked call, exactly as Claude Code does: it keeps
        // `./ra state approve` and `./ra paper use` human-only.
        env: { ...process.env, CLAUDECODE: "1", PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
        windowsHide: true,
      })
    } catch {
      resolve({ code: 2, stdout: "", stderr: "could not start bash" })
      return
    }
    let stdout = ""
    let stderr = ""
    child.stdout?.on("data", (d) => (stdout += d.toString()))
    child.stderr?.on("data", (d) => (stderr += d.toString()))
    child.on("error", () => resolve({ code: 2, stdout, stderr: stderr || "bash is not available" }))
    child.on("close", (code) => resolve({ code: code ?? 2, stdout, stderr }))
    try {
      if (payload !== undefined) {
        child.stdin?.write(JSON.stringify(payload))
        child.stdin?.end()
      } else {
        child.stdin?.end()
      }
    } catch {
      /* the process is gone; `close` still resolves */
    }
  })
}

function runHook(ws: string, event: string, payload: unknown): Promise<Run> {
  return run(ws, ["ra", "hook", event], payload)
}

function reason(r: Run): string {
  const text = (r.stderr || r.stdout || "").trim()
  return text.startsWith("[workspace guard]")
    ? text
    : `${BLOCK}${text || "the workspace guard refused this action."}`
}

// --------------------------------------------------------------- path translation

let wsNative = ""
let wsPosix = ""
let mountRoot = ""

/** The POSIX form of the workspace root, as the guard's Linux Python sees it. */
async function initPaths(ws: string): Promise<void> {
  wsNative = ws
  const probe = await run(ws, ["-c", "pwd"])
  wsPosix = probe.stdout.trim() || ws
  // Derive the WSL mount root ("/mnt/c") by matching the native path's tail against the
  // POSIX one, so the mapping is verified rather than assumed.
  const nativeRest = wsNative.replace(/^[A-Za-z]:[\\/]/, "").replace(/\\/g, "/").replace(/\/+$/, "")
  const posixRest = wsPosix.replace(/^\/mnt\/[a-z]\//, "").replace(/\/+$/, "")
  mountRoot = posixRest && nativeRest.endsWith(posixRest)
    ? wsPosix.slice(0, wsPosix.length - posixRest.length).replace(/\/+$/, "")
    : ""
}

/** Native (Windows) absolute path for a tool input path. */
function absNative(p: unknown): string | undefined {
  if (typeof p !== "string" || !p) return undefined
  if (path.isAbsolute(p)) return p
  const joined = path.resolve(wsNative, p)
  if (existsSync(joined)) return joined
  const fromCwd = path.resolve(process.cwd(), p)
  return existsSync(fromCwd) ? fromCwd : joined
}

/** Native -> POSIX (WSL) path, as the guard's Linux Python needs it. */
function toPosix(p: string | undefined): string | undefined {
  if (!p) return p
  if (p.startsWith("/")) return p
  const m = p.match(/^([A-Za-z]):[\\/](.*)$/)
  if (m) {
    const rest = m[2].replace(/\\/g, "/")
    return mountRoot ? `${mountRoot}/${m[1].toLowerCase()}/${rest}` : `/${m[1].toLowerCase()}/${rest}`
  }
  return p
}

/** Workspace-relative POSIX path for a tool input path. */
function posixPath(p: unknown): string | undefined {
  return toPosix(absNative(p))
}

/** Strip the workspace prefix from a shell command so the guard sees it workspace-relative. */
function relativize(cmd: string): string {
  if (!cmd || !wsNative) return cmd
  const forms = [wsNative, wsNative.replace(/\\/g, "/"), wsPosix]
  for (const f of forms) {
    if (!f) continue
    cmd = cmd.split(f + "/").join("").split(f + "\\").join("")
  }
  return cmd
}

// ------------------------------------------------------------ payload translation

type Payload = Record<string, unknown>

/** OpenCode tool call -> the payload shape `scripts/ra/hooks.py` expects. */
function toPayload(tool: string, input: any, sessionID: string): Payload | null {
  const base: Payload = { session_id: sessionID, cwd: wsPosix }
  switch (tool) {
    case "edit":
      return {
        ...base,
        tool_name: "Edit",
        tool_input: {
          file_path: posixPath(input?.path),
          old_string: input?.oldString,
          new_string: input?.newString,
          replace_all: input?.replaceAll,
        },
      }
    case "write":
      return { ...base, tool_name: "Write", tool_input: { file_path: posixPath(input?.path), content: input?.content } }
    case "read":
      return { ...base, tool_name: "Read", tool_input: { file_path: posixPath(input?.path) } }
    case "glob":
      return { ...base, tool_name: "Glob", tool_input: { path: posixPath(input?.path), pattern: input?.pattern } }
    case "grep":
      return { ...base, tool_name: "Grep", tool_input: { path: posixPath(input?.path), pattern: input?.pattern } }
    case "shell":
    case "bash":
      return { ...base, tool_name: "Bash", tool_input: { command: relativize(input?.command ?? "") } }
    case "skill":
      return { ...base, tool_name: "Skill", tool_input: { skill: input?.id } }
    default:
      return null
  }
}

// ------------------------------------------------------------------- the plugin

export default Plugin.define({
  id: "ra-guard",

  async setup(ctx) {
    const ws = findWorkspace()
    if (!ws) {
      console.error("[ra-guard] workspace not found (no `ra` + `scripts/cli.py` above this plugin); guardrails OFF")
      return
    }
    await initPaths(ws)

    // Messages waiting to be shown to the model on the next request.
    const pending: string[] = []
    const announce = (text: string) => {
      if (text && text.trim()) pending.push(text.trim())
    }

    // --- SessionStart (once per session) and UserPromptSubmit.
    const started = new Set<string>()
    await ctx.session.hook("prompt", async (event) => {
      const sid = event.sessionID ?? ""
      const text = event.prompt?.text ?? ""

      if (sid && !started.has(sid)) {
        started.add(sid)
        const r = await runHook(ws, "session-start", { session_id: sid, source: "startup" })
        if (r.stdout?.trim()) announce(r.stdout.trim())
      }

      // The hook records the human's PAPER / NEW PAPER / APPROVE / REJECT lines and prints the
      // pipeline status. It never rejects a prompt.
      const r = await runHook(ws, "prompt", { session_id: sid, prompt: text })
      if (r.stdout?.trim()) announce(r.stdout.trim())
      if (r.code === 2 && r.stderr?.trim()) announce(r.stderr.trim())
    })

    // --- Surface the session banner, hook output and guard failures to the model.
    await ctx.session.hook("context", (event) => {
      if (!pending.length) return
      const text = pending.join("\n\n")
      pending.length = 0
      event.system.push({ type: "text", text })
    })

    // --- PreToolUse equivalents.
    await ctx.tool.hook("execute.before", async (event) => {
      const tool = event.tool
      const sessionID = (event as any).sessionID ?? (event as any).sessionId ?? ""
      const input = (event as any).input ?? {}

      if (tool === "patch") {
        throw new Error(
          `${BLOCK}the \`patch\` tool cannot be checked by the workspace guard (its multi-file diff ` +
            `format is not understood by \`ra hook pre-edit\`). Use \`edit\` or \`write\` on one file at a time.`,
        )
      }

      let eventName: string
      if (tool === "edit" || tool === "write") eventName = "pre-edit"
      else if (tool === "read" || tool === "glob" || tool === "grep") eventName = "pre-read"
      else if (tool === "shell" || tool === "bash") eventName = "pre-bash"
      else if (tool === "skill") eventName = "pre-skill"
      else return

      const payload = toPayload(tool, input, sessionID)
      if (!payload) return

      const r = await runHook(ws, eventName, payload)
      if (r.code === 2) throw new Error(reason(r))
    })

    // --- PostToolUse equivalent: re-verify citations/abstract/numbers and compile the paper
    //     after every edit, plus the LOCKED-region backstop that Claude Code runs on Stop.
    await ctx.tool.hook("execute.after", async (event) => {
      const tool = event.tool
      const sessionID = (event as any).sessionID ?? (event as any).sessionId ?? ""
      const input = (event as any).input ?? {}

      if (tool === "edit" || tool === "write") {
        const payload = toPayload(tool, input, sessionID)
        if (payload) {
          const r = await runHook(ws, "post-edit", payload)
          if (r.code === 2) {
            announce(
              `[workspace guard] post-edit checks FAILED after editing ${(payload.tool_input as any)?.file_path} ` +
                `(the edit was applied; fix this next):\n${(r.stderr || r.stdout).trim()}`,
            )
          } else if (r.stdout?.trim()) {
            announce(r.stdout.trim())
          }
        }
      }

      // Stop -> lock backstop (OpenCode has no stop hook; check after each tool instead).
      const lock = await runHook(ws, "stop", { session_id: sessionID })
      if (lock.code === 2 && lock.stderr?.trim()) announce(lock.stderr.trim())
    })
  },
})
