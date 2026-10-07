// Fails if regenerating the API client changes it, meaning the API changed but
// `pnpm gen:client` wasn't run. Compares file contents before/after, so it works
// with uncommitted changes too.
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const root = "packages/api-client";
const targets = [join(root, "openapi.json"), join(root, "src", "gen")];

function snapshot() {
  const hash = createHash("sha256");
  const walk = (p) => {
    if (statSync(p).isDirectory()) for (const f of readdirSync(p).sort()) walk(join(p, f));
    else hash.update(p).update(readFileSync(p));
  };
  targets.forEach(walk);
  return hash.digest("hex");
}

const before = snapshot();
execSync("pnpm gen:client", { stdio: "ignore" });
if (snapshot() !== before) {
  console.error("API client was out of date and has now been regenerated. Review and commit packages/api-client.");
  process.exit(1);
}
console.log("API client is up to date.");
