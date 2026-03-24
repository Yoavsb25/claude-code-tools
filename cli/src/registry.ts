// eslint-disable-next-line @typescript-eslint/no-var-requires
const fetch = require("node-fetch") as typeof import("node-fetch").default;
import * as fs from "fs";
import * as path from "path";

const REGISTRY_URL =
  "https://raw.githubusercontent.com/Yoavsb25/claude-code-tools/main/registry.json";

export interface ManifestFile {
  src: string;
  dest: string;
}

export interface Tool {
  name: string;
  version: string;
  description: string;
  type: "skill" | "tool";
  category: string;
  complexity: "simple" | "intermediate" | "advanced";
  tags: string[];
  path: string;
  install: { files: ManifestFile[] };
  requirements: {
    platform: string;
    mcp_servers: string[];
    env_vars: string[];
    python?: string;
  };
}

export interface Registry {
  generated: string;
  count: number;
  tools: Tool[];
}

export async function fetchRegistry(): Promise<Registry> {
  try {
    const res = await fetch(REGISTRY_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Registry;
  } catch {
    // Fall back to local registry if present (for dev/offline use)
    const localPath = path.join(__dirname, "..", "..", "registry.json");
    if (fs.existsSync(localPath)) {
      return JSON.parse(fs.readFileSync(localPath, "utf-8")) as Registry;
    }
    throw new Error(
      "Could not fetch registry. Check your internet connection or clone the repo locally."
    );
  }
}
