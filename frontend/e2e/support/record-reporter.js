// Writes a run log to docs/test-cases/runs/, one row per spec, for the
// test-execution record. Used by `npm run test:e2e:record` only, so ad hoc
// runs while writing specs leave no files behind.
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RUNS_DIR = path.join(REPO_ROOT, "docs", "test-cases", "runs");

function git(args) {
  try {
    return execSync(`git ${args}`, { cwd: REPO_ROOT, encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

function singaporeTime(date) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Singapore",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map(({ type, value }) => [type, value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

const cell = (text) => String(text).replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();

export default class RecordReporter {
  onBegin(config) {
    this.started = new Date();
    this.baseURL = config.projects[0]?.use?.baseURL;
    this.rows = [];
  }

  onTestEnd(test, result) {
    const title = test.title;
    const caseIds = title.match(/TC-[A-Z]+-\d+/g) ?? [];
    const check = title.replace(/^(TC-[A-Z]+-\d+\s+)+/, "");
    const detail = result.status === "passed" ? "" : (result.error?.message ?? "").split("\n")[0].slice(0, 200);
    this.rows.push({ caseIds: caseIds.join(", ") || "—", check, status: result.status, detail });
  }

  onEnd() {
    const { date, time } = singaporeTime(this.started);
    const commit = git("rev-parse --short HEAD") || "unknown";
    const dirty = Boolean(git("status --porcelain --untracked-files=no"));
    const passed = this.rows.filter((row) => row.status === "passed").length;
    const seconds = Math.round((Date.now() - this.started.getTime()) / 1000);

    const lines = [
      `# Automated live checks — ${date} ${time} SGT`,
      "",
      "| | |",
      "|---|---|",
      "| Method | Playwright, `frontend/e2e/` (real browser, real backend, live Supabase) |",
      `| Result | **${passed}/${this.rows.length} passed** |`,
      `| Commit | \`${commit}\`${dirty ? " + uncommitted changes" : ""} on \`${git("branch --show-current")}\` |`,
      `| Frontend | \`${this.baseURL}\` |`,
      `| Backend | \`${process.env.E2E_API_URL || "http://localhost:8000/api/v1"}\` |`,
      `| Run by | ${git("config user.name") || "unknown"} |`,
      `| Duration | ${seconds}s |`,
      "",
      "| Case | Check | Result | Detail |",
      "|---|---|---|---|",
      ...this.rows.map(
        (row) =>
          `| ${row.caseIds} | ${cell(row.check)} | ${row.status === "passed" ? "Pass" : `**${row.status}**`} | ${cell(row.detail)} |`,
      ),
    ];

    mkdirSync(RUNS_DIR, { recursive: true });
    const file = path.join(RUNS_DIR, `${date}-${time.replace(":", "")}-e2e-${commit}.md`);
    writeFileSync(file, lines.join("\n") + "\n");
    console.log(`Run log: ${path.relative(REPO_ROOT, file)}`);
  }
}
