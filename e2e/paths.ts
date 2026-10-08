import path from "node:path";

/** Files shared between the config, the API's e2e mode and the tests (all git-ignored). */
export const WORLD_FILE = path.join(import.meta.dirname, ".world.json");
export const OUTBOX_FILE = path.join(import.meta.dirname, ".outbox.jsonl");
