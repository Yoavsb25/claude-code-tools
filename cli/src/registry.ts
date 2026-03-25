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

export function validateRegistry(data: unknown): asserts data is Registry {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error("Invalid registry: expected a JSON object at top level.");
  }
  const obj = data as Record<string, unknown>;
  if (!Array.isArray(obj.tools)) {
    throw new Error("Invalid registry: 'tools' must be an array.");
  }
  for (let i = 0; i < obj.tools.length; i++) {
    const tool = obj.tools[i] as Record<string, unknown>;
    if (typeof tool.name !== "string" || !tool.name) {
      throw new Error(`Invalid registry: tool at index ${i} missing valid 'name'.`);
    }
    if (typeof tool.version !== "string") {
      throw new Error(`Invalid registry: tool "${tool.name}" missing 'version'.`);
    }
    if (typeof tool.install !== "object" || tool.install === null) {
      throw new Error(`Invalid registry: tool "${tool.name}" missing 'install'.`);
    }
    const install = tool.install as Record<string, unknown>;
    if (!Array.isArray(install.files)) {
      throw new Error(`Invalid registry: tool "${tool.name}".install.files must be an array.`);
    }
    for (const file of install.files as Array<Record<string, unknown>>) {
      if (typeof file.src !== "string" || typeof file.dest !== "string") {
        throw new Error(`Invalid registry: tool "${tool.name}" file entry missing 'src' or 'dest'.`);
      }
      if (file.src.includes("../") || file.src.includes("..\\")) {
        throw new Error(`Security: tool "${tool.name}" has traversal sequence in src: "${file.src}".`);
      }
      if (file.dest.includes("../") || file.dest.includes("..\\")) {
        throw new Error(`Security: tool "${tool.name}" has traversal sequence in dest: "${file.dest}".`);
      }
    }
    const req = tool.requirements as Record<string, unknown>;
    if (!req || !Array.isArray(req.mcp_servers) || !Array.isArray(req.env_vars)) {
      throw new Error(`Invalid registry: tool "${tool.name}".requirements missing mcp_servers/env_vars arrays.`);
    }
  }
}

export async function fetchRegistry(): Promise<Registry> {
  try {
    const res = await fetch(REGISTRY_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const parsed = await res.json();
    validateRegistry(parsed);
    return parsed;
  } catch {
    // Fall back to local registry if present (for dev/offline use)
    const localPath = path.join(__dirname, "..", "..", "registry.json");
    if (fs.existsSync(localPath)) {
      const parsed = JSON.parse(fs.readFileSync(localPath, "utf-8"));
      validateRegistry(parsed);
      return parsed;
    }
    throw new Error(
      "Could not fetch registry. Check your internet connection or clone the repo locally."
    );
  }
}
