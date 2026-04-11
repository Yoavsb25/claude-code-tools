#!/usr/bin/env ts-node
// Reads all tools/<name>/manifest.json files and outputs registry.json and updates README.md.
// Run: npx ts-node scripts/generate-registry.ts

import * as fs from "fs";
import * as path from "path";

const TOOLS_DIR = path.join(__dirname, "..", "tools");
const REGISTRY_PATH = path.join(__dirname, "..", "registry.json");
const README_PATH = path.join(__dirname, "..", "README.md");

interface ManifestFile {
  src: string;
  dest: string;
}

interface Manifest {
  name: string;
  version: string;
  description: string;
  type: "skill" | "tool";
  category: string;
  complexity: "simple" | "intermediate" | "advanced";
  tags: string[];
  install: { files: ManifestFile[] };
  requirements: {
    platform: string;
    mcp_servers: string[];
    env_vars: string[];
    python?: string;
  };
}

interface RegistryEntry extends Manifest {
  path: string;
}

function generate() {
  if (!fs.existsSync(TOOLS_DIR)) {
    fs.mkdirSync(TOOLS_DIR, { recursive: true });
  }

  const toolDirs = fs
    .readdirSync(TOOLS_DIR)
    .filter((d) => fs.statSync(path.join(TOOLS_DIR, d)).isDirectory());

  const tools: RegistryEntry[] = [];

  for (const toolDir of toolDirs) {
    const manifestPath = path.join(TOOLS_DIR, toolDir, "manifest.json");
    if (!fs.existsSync(manifestPath)) {
      console.warn(`⚠️  No manifest.json in tools/${toolDir} — skipping`);
      continue;
    }
    const manifest: Manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    tools.push({ ...manifest, path: `tools/${toolDir}` });
    console.log(`✅  ${manifest.name} (${manifest.type}, ${manifest.complexity})`);
  }

  tools.sort((a, b) => a.name.localeCompare(b.name));

  const registry = {
    generated: new Date().toISOString(),
    count: tools.length,
    tools,
  };

  fs.writeFileSync(REGISTRY_PATH, JSON.stringify(registry, null, 2) + "\n");
  console.log(`\n📦  registry.json written — ${tools.length} tools indexed`);

  updateReadme(tools);
}

const COMPLEXITY_ORDER = { simple: 0, intermediate: 1, advanced: 2 };

function updateReadme(tools: RegistryEntry[]) {
  const readme = fs.readFileSync(README_PATH, "utf-8");

  const sorted = [...tools].sort((a, b) => {
    const cDiff = COMPLEXITY_ORDER[a.complexity] - COMPLEXITY_ORDER[b.complexity];
    return cDiff !== 0 ? cDiff : a.name.localeCompare(b.name);
  });

  const rows = sorted
    .map((t) => `| [${t.name}](./tools/${t.name}/) | ${t.type} | ${t.category} | ${t.complexity} | ${t.description} |`)
    .join("\n");

  const table =
    `| Name | Type | Category | Complexity | Description |\n` +
    `|------|------|----------|------------|-------------|\n` +
    rows;

  const updated = readme.replace(
    /(\## What's inside\n\n)[\s\S]*?(\n\n---)/,
    `$1${table}$2`
  );

  fs.writeFileSync(README_PATH, updated);
  console.log(`📝  README.md "What's inside" updated — ${tools.length} entries`);
}

generate();
