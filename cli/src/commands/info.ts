import chalk from "chalk";
import { fetchRegistry } from "../registry.js";

export async function infoCommand(name: string): Promise<void> {
  const registry = await fetchRegistry();
  const tool = registry.tools.find((t) => t.name === name);

  if (!tool) {
    console.error(chalk.red(`Tool "${name}" not found in registry.`));
    console.log(chalk.dim(`Run "npx @yoavsb25/claude-tools list" to see available tools.`));
    process.exit(1);
  }

  console.log();
  console.log(chalk.bold.white(`  ${tool.name}`) + chalk.dim(` v${tool.version}`));
  console.log(`  ${chalk.dim(tool.description)}`);
  console.log();

  const row = (label: string, value: string) =>
    console.log(`  ${chalk.bold(label.padEnd(14))} ${value}`);

  row("Type", tool.type === "skill" ? chalk.cyan("skill") : chalk.magenta("tool"));
  row("Category", tool.category);
  row(
    "Complexity",
    tool.complexity === "simple"
      ? chalk.green("simple")
      : tool.complexity === "intermediate"
      ? chalk.yellow("intermediate")
      : chalk.red("advanced")
  );
  row("Tags", tool.tags.join(", "));
  row("Platform", tool.requirements.platform);

  if (tool.requirements.mcp_servers.length > 0) {
    row("MCP servers", tool.requirements.mcp_servers.join(", "));
  }
  if (tool.requirements.env_vars.length > 0) {
    row("Env vars", tool.requirements.env_vars.join(", "));
  }
  if (tool.requirements.python) {
    row("Python", tool.requirements.python);
  }

  console.log();
  console.log(chalk.bold("  Files installed:"));
  for (const file of tool.install.files) {
    console.log(`    ${chalk.dim(file.src)} → ${chalk.green(file.dest)}`);
  }

  console.log();
  console.log(
    `  ${chalk.bold("Source:")} https://github.com/Yoavsb25/claude-code-tools/tree/main/${tool.path}`
  );

  console.log();
  console.log(
    `  ${chalk.dim("Install:")} npx @yoavsb25/claude-tools install ${tool.name}`
  );
  console.log();
}
