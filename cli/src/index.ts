import { Command } from "commander";
import { listCommand } from "./commands/list.js";
import { infoCommand } from "./commands/info.js";
import { installCommand } from "./commands/install.js";

const program = new Command();

program
  .name("claude-tools")
  .description("Browse and install Claude Code skills from the claude-code-tools registry")
  .version("1.0.0");

program
  .command("list")
  .description("List all available tools and skills")
  .option("-c, --category <category>", "Filter by category (e.g. shopping, finance, productivity)")
  .option("-t, --type <type>", "Filter by type: skill or tool")
  .option("-x, --complexity <complexity>", "Filter by complexity: simple, intermediate, advanced")
  .action(listCommand);

program
  .command("info <name>")
  .description("Show detailed information about a tool")
  .action(infoCommand);

program
  .command("install <name>")
  .description("Install a tool into your Claude Code setup")
  .action(installCommand);

program.parseAsync(process.argv).catch((err) => {
  console.error(err.message);
  process.exit(1);
});
