import * as os from "os";
import * as path from "path";
import { resolveAndValidateDest } from "./install.js";

const BASE = path.join(os.homedir(), ".claude", "skills");

describe("resolveAndValidateDest", () => {
  it("accepts a dest inside ~/.claude/skills/", () => {
    const result = resolveAndValidateDest("~/.claude/skills/my-tool/SKILL.md");
    expect(result).toBe(path.join(BASE, "my-tool", "SKILL.md"));
  });

  it("rejects .. traversal escape", () => {
    expect(() =>
      resolveAndValidateDest("~/.claude/skills/../../.ssh/authorized_keys")
    ).toThrow(/outside the allowed install directory/);
  });

  it("rejects absolute path outside base", () => {
    expect(() => resolveAndValidateDest("/etc/passwd")).toThrow(
      /must be a tilde-relative path starting with "~\/"/
    );
  });

  it("rejects ~ path that doesn't reach skills/", () => {
    expect(() => resolveAndValidateDest("~/.bashrc")).toThrow(
      /outside the allowed install directory/
    );
  });
});
