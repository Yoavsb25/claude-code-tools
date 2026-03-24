export interface RegistryTool {
  name: string
  version: string
  description: string
  type: 'skill' | 'tool'
  category: string
  complexity: 'simple' | 'intermediate' | 'advanced'
  tags: string[]
  install: { files: { src: string; dest: string }[] }
  requirements: {
    platform: string
    mcp_servers: string[]
    env_vars: string[]
    python?: string
  }
  path: string
}

export interface Registry {
  generated: string
  count: number
  tools: RegistryTool[]
}
