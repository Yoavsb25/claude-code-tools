import chalk from "chalk";
import { fetchRegistry, Tool } from "../registry.js";

interface ListOptions {
  category?: string;
  type?: string;
  complexity?: string;
}

const COMPLEXITY_ORDER = { simple: 0, intermediate: 1, advanced: 2 };

function formatComplexity(c: string): string {
  if (c === "simple") return chalk.green("simple");
  if (c === "intermediate") return chalk.yellow("intermediate");
  return chalk.red("advanced");
}

function formatType(t: string): string {
  return t === "skill" ? chalk.cyan("skill") : chalk.magenta("tool");
}

export async function listCommand(options: ListOptions): Promise<void> {
  const registry = await fetchRegistry();
  let tools: Tool[] = registry.tools;

  if (options.category) {
    tools = tools.filter((t) =>
      t.category.toLowerCase().includes(options.category!.toLowerCase())
    );
  }
  if (options.type) {
    tools = tools.filter((t) => t.type === options.type);
  }
  if (options.complexity) {
    tools = tools.filter((t) => t.complexity === options.complexity);
  }

  if (tools.length === 0) {
    console.log(chalk.yellow("No tools match the given filters."));
    return;
  }

  tools.sort(
    (a, b) =>
      COMPLEXITY_ORDER[a.complexity] - COMPLEXITY_ORDER[b.complexity] ||
      a.name.localeCompare(b.name)
  );

  const nameWidth = Math.max(...tools.map((t) => t.name.length), 4) + 2;
  const catWidth = Math.max(...tools.map((t) => t.category.length), 8) + 2;

  console.log();
  console.log(
    chalk.bold(
      `${"NAME".padEnd(nameWidth)}${"TYPE".padEnd(14)}${"CATEGORY".padEnd(catWidth)}${"COMPLEXITY".padEnd(16)}DESCRIPTION`
    )
  );
  console.log("─".repeat(nameWidth + 14 + catWidth + 16 + 40));

  for (const tool of tools) {
    const name = chalk.white.bold(tool.name.padEnd(nameWidth));
    const type = formatType(tool.type).padEnd(20);
    const cat = tool.category.padEnd(catWidth);
    const complexity = formatComplexity(tool.complexity).padEnd(22);
    const desc =
      tool.description.length > 60
        ? tool.description.slice(0, 57) + "..."
        : tool.description;
    console.log(`${name}${type}${cat}${complexity}${desc}`);
  }

  console.log();
  console.log(
    chalk.dim(
      `${tools.length} of ${registry.count} tools shown  ·  install: npx @yoavsb25/claude-tools install <name>`
    )
  );
  console.log();
}
