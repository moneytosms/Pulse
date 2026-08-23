#!/usr/bin/env node
// Claude Code statusLine. Reads session JSON on stdin, prints two lines.
// Port of dotfiles/dev/.claude/statusline-command.sh — see spec for segment table.

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, statSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const GREEN = "\x1b[32m", YELLOW = "\x1b[33m", RED = "\x1b[31m", CYAN = "\x1b[36m", DIM = "\x1b[2m", RESET = "\x1b[0m";

function readStdin() {
  try {
    return readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function git(args, cwd) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

function countLines(s) {
  if (!s) return 0;
  return s.split("\n").filter(Boolean).length;
}

// 5s-TTL cache of branch/staged/modified, keyed by session_id, in os.tmpdir().
function getGitInfo(sessionId, cwd) {
  if (!cwd || !existsSync(cwd)) return { branch: "", staged: 0, modified: 0 };
  const cacheFile = path.join(tmpdir(), `statusline-git-cache-${sessionId || "default"}`);
  let cached = null;
  try {
    const age = (Date.now() - statSync(cacheFile).mtimeMs) / 1000;
    if (age <= 5) cached = JSON.parse(readFileSync(cacheFile, "utf8"));
  } catch {
    // no cache or expired
  }
  if (cached) return cached;

  let info = { branch: "", staged: 0, modified: 0 };
  if (git(["rev-parse", "--git-dir"], cwd) !== null) {
    const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) || "";
    const staged = countLines(git(["diff", "--cached", "--numstat"], cwd));
    const modified = countLines(git(["diff", "--numstat"], cwd));
    info = { branch, staged, modified };
  }
  try {
    writeFileSync(cacheFile, JSON.stringify(info));
  } catch {
    // best-effort cache
  }
  return info;
}

// "claude-opus-5" -> "Opus 5"; "claude-haiku-4-5-20251001" -> "Haiku 4.5"
function modelName(model) {
  const id = model?.id;
  if (typeof id !== "string" || !id.includes("-")) return model?.display_name || "";
  const parts = id.split("-");
  if (parts[0] === "claude") parts.shift();
  const family = parts.shift();
  if (!family) return model?.display_name || "";
  const versionParts = [];
  for (const p of parts) {
    if (/^\d{5,}$/.test(p)) break; // date-like suffix, stop
    versionParts.push(p);
  }
  const name = family.charAt(0).toUpperCase() + family.slice(1);
  return versionParts.length ? `${name} ${versionParts.join(".")}` : name || model?.display_name || "";
}

function bar(pct) {
  const p = Number.isFinite(pct) ? Math.min(100, Math.max(0, pct)) : 0;
  const filled = Math.round(p / 10);
  const color = p >= 90 ? RED : p >= 70 ? YELLOW : GREEN;
  return `${color}[${"█".repeat(filled)}${"░".repeat(10 - filled)}]${RESET}`;
}

function main() {
  const raw = readStdin();
  if (!raw.trim()) return;
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return;
  }

  const dir = data?.workspace?.current_dir;
  const sessionId = data?.session_id;
  const { branch, staged, modified } = getGitInfo(sessionId, dir);

  const line1 = [];
  if (dir) line1.push(`${CYAN}${path.basename(dir)}${RESET}`);

  if (branch) {
    const gitParts = [`${GREEN}br:${branch}${RESET}`];
    if (staged > 0) gitParts.push(`${GREEN}+${staged}${RESET}`);
    if (modified > 0) gitParts.push(`${YELLOW}~${modified}${RESET}`);
    line1.push(gitParts.join(" "));
  }

  const owner = data?.workspace?.repo?.owner;
  const repoName = data?.workspace?.repo?.name;
  if (owner && repoName) line1.push(`${DIM}${owner}/${repoName}${RESET}`);

  const worktree = data?.worktree?.name || data?.workspace?.git_worktree;
  if (worktree) line1.push(`${DIM}wt:${worktree}${RESET}`);

  const prNumber = data?.pr?.number;
  if (prNumber) {
    const state = data?.pr?.review_state;
    line1.push(`PR#${prNumber}${state ? " " + state : ""}`);
  }

  const line2 = [];
  const model = modelName(data?.model);
  const effort = data?.effort?.level;
  if (model || effort) line2.push([model, effort].filter(Boolean).join(" "));

  const totalInput = data?.context_window?.total_input_tokens;
  const windowSize = data?.context_window?.context_window_size;
  const usedPct = data?.context_window?.used_percentage;
  const pctNum = typeof usedPct === "number" && Number.isFinite(usedPct) ? usedPct : 0;
  let tokenStr;
  if (typeof totalInput === "number" && typeof windowSize === "number" && totalInput > 0 && windowSize > 0) {
    tokenStr = `${(totalInput / 1000).toFixed(1)}k/${Math.round(windowSize / 1000)}k ${Math.round(pctNum)}%`;
  } else {
    tokenStr = "--";
  }
  line2.push(`${bar(pctNum)} ${tokenStr}`);

  const fiveHour = data?.rate_limits?.five_hour?.used_percentage;
  const sevenDay = data?.rate_limits?.seven_day?.used_percentage;
  const limitParts = [];
  if (typeof fiveHour === "number" && Number.isFinite(fiveHour)) limitParts.push(`5h:${Math.round(fiveHour)}%`);
  if (typeof sevenDay === "number" && Number.isFinite(sevenDay)) limitParts.push(`7d:${Math.round(sevenDay)}%`);
  if (limitParts.length) line2.push(limitParts.join(" "));

  if (line1.length) console.log(line1.join("  "));
  if (line2.length) console.log(line2.join("  "));
}

main();
