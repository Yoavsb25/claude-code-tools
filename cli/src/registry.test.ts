import { validateRegistry } from "./registry.js";

describe("validateRegistry", () => {
  const validTool = {
    name: "my-tool",
    version: "1.0.0",
    description: "A test tool",
    type: "skill",
    category: "productivity",
    complexity: "simple",
    tags: ["test"],
    path: "tools/my-tool",
    install: { files: [{ src: "SKILL.md", dest: "~/.claude/skills/my-tool/SKILL.md" }] },
    requirements: { platform: "any", mcp_servers: [], env_vars: [] },
  };

  it("accepts a well-formed registry", () => {
    expect(() => validateRegistry({ generated: "2025-01-01", count: 1, tools: [validTool] })).not.toThrow();
  });

  it("rejects null", () => {
    expect(() => validateRegistry(null)).toThrow(/Invalid registry/);
  });

  it("rejects missing tools array", () => {
    expect(() => validateRegistry({ count: 0 })).toThrow(/tools.*array/i);
  });

  it("rejects tool with no name", () => {
    const bad = { ...validTool, name: "" };
    expect(() => validateRegistry({ tools: [bad] })).toThrow(/name/i);
  });

  it("rejects src with traversal", () => {
    const bad = { ...validTool, install: { files: [{ src: "../../etc/passwd", dest: "~/.claude/skills/my-tool/SKILL.md" }] } };
    expect(() => validateRegistry({ tools: [bad] })).toThrow(/traversal/i);
  });

  it("rejects dest with traversal", () => {
    const bad = { ...validTool, install: { files: [{ src: "SKILL.md", dest: "~/.claude/skills/../../.ssh/authorized_keys" }] } };
    expect(() => validateRegistry({ tools: [bad] })).toThrow(/traversal/i);
  });
});
