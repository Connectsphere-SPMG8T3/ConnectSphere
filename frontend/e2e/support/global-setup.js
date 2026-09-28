import { API_URL } from "./fixtures.js";
import { deleteThrowawayAccounts } from "./throwaway.js";

// Fail in one clear line when a server isn't running, rather than letting
// every spec time out on its first navigation.
export default async function globalSetup(config) {
  const baseURL = config.projects[0].use.baseURL;
  const healthURL = API_URL.replace(/\/api\/v1\/?$/, "") + "/health";

  for (const [name, url, hint] of [
    ["Frontend", baseURL, "npm run dev, or set E2E_BASE_URL"],
    ["Backend", healthURL, "uvicorn app.main:app from backend/, or set E2E_API_URL"],
  ]) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      throw new Error(`${name} not reachable at ${url} (${error.message}). Start it: ${hint}.`);
    }
  }

  // Sign-up specs create live-check+… accounts; clear any an interrupted
  // run left behind, and clear this run's when it finishes.
  deleteThrowawayAccounts();
  return () => deleteThrowawayAccounts();
}
