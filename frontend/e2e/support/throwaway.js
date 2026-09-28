// Throwaway accounts for the sign-up specs. They share one email pattern with
// backend/scripts/verify_live.py, and every account matching it is deleted,
// along with everything it owns, before and after a run.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PROJECT_REF = "vuiryrzzyfecjqftwicj";
const PREFIX = "live-check+";
const DOMAIN = "@connectsphere.dev";

const runId = new Date().toISOString().replace(/\D/g, "").slice(0, 14);

export const THROWAWAY_PASSWORD = "Cs1234" + "live";

export function throwawayEmail(tag) {
  return `${PREFIX}e2e-${runId}-${tag}${DOMAIN}`;
}

export function deleteThrowawayAccounts() {
  execFileSync(
    "supabase",
    [
      "db",
      "query",
      "--linked",
      "--project-ref",
      PROJECT_REF,
      `delete from auth.users where email like '${PREFIX}%${DOMAIN}'`,
    ],
    { cwd: REPO_ROOT, stdio: "pipe" },
  );
}
