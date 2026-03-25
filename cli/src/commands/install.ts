import chalk from "chalk";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const fetch = require("node-fetch") as typeof import("node-fetch").default;
import { fetchRegistry } from "../registry.js";

const REPO_RAW =
  "https://raw.githubusercontent.com/Yoavsb25/claude-code-tools/main";

const ALLOWED_BASE = path.resolve(os.homedir(), ".claude", "skills");

export function resolveAndValidateDest(dest: string): string {
  const expanded = dest.startsWith("~/")
    ? path.join(os.homedir(), dest.slice(2))
    : dest;
  const resolved = path.resolve(expanded);
  if (resolved !== ALLOWED_BASE && !resolved.startsWith(ALLOWED_BASE + path.sep)) {
    throw new Error(
      `Security: destination "${dest}" resolves to "${resolved}", which is outside the allowed install directory (${ALLOWED_BASE}). Installation aborted.`
    );
  }
  return resolved;
}

async function downloadFile(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to download ${url}: HTTP ${res.status}`);
  return res.text();
}

export async function installCommand(name: string): Promise<void> {
  const registry = await fetchRegistry();
  const tool = registry.tools.find((t) => t.name === name);

  if (!tool) {
    console.error(chalk.red(`Tool "${name}" not found in registry.`));
    console.log(chalk.dim(`Run "npx @yoavsb25/claude-tools list" to see available tools.`));
    process.exit(1);
  }

  console.log();
  console.log(chalk.bold(`Installing ${tool.name} v${tool.version}...`));
  console.log();

  // Platform check
  if (tool.requirements.platform !== "any") {
    const platform = process.platform;
    const expectedPlatform = tool.requirements.platform;
    const platformMap: Record<string, string> = { macos: "darwin" };
    if (platform !== (platformMap[expectedPlatform] ?? expectedPlatform)) {
      console.warn(
        chalk.yellow(
          `⚠  This tool is designed for ${expectedPlatform} but you are on ${platform}.`
        )
      );
      console.warn(chalk.dim("   Some features may not work as expected.\n"));
    }
  }

  // MCP server warnings
  if (tool.requirements.mcp_servers.length > 0) {
    console.log(chalk.yellow("⚠  Required MCP servers (must be configured in Claude Code):"));
    for (const mcp of tool.requirements.mcp_servers) {
      console.log(`   • ${mcp}`);
    }
    console.log();
  }

  // Env var warnings
  if (tool.requirements.env_vars.length > 0) {
    console.log(chalk.yellow("⚠  Required environment variables:"));
    for (const envVar of tool.requirements.env_vars) {
      const set = process.env[envVar] !== undefined;
      console.log(
        `   • ${envVar} ${set ? chalk.green("(set)") : chalk.red("(not set)")}`
      );
    }
    console.log();
  }

  // Download and write files
  for (const file of tool.install.files) {
    const destPath = resolveAndValidateDest(file.dest);
    const destDir = path.dirname(destPath);

    const fileUrl = `${REPO_RAW}/${tool.path}/${file.src}`;
    process.stdout.write(`  Downloading ${file.src}...`);

    const content = await downloadFile(fileUrl);
    fs.mkdirSync(destDir, { recursive: true });
    fs.writeFileSync(destPath, content, "utf-8");

    console.log(chalk.green(" ✓"));
    console.log(chalk.dim(`    → ${destPath}`));
  }

  console.log();
  console.log(chalk.green.bold(`✓ ${tool.name} installed successfully!`));
  console.log();
  console.log(chalk.bold("Next steps:"));
  console.log(
    `  Run the skill in Claude Code: ${chalk.cyan(`/${tool.name}`)}`
  );
  if (tool.requirements.mcp_servers.length > 0) {
    console.log(
      `  ${chalk.dim("Make sure these MCP servers are configured:")} ${tool.requirements.mcp_servers.join(", ")}`
    );
  }
  console.log();
}
