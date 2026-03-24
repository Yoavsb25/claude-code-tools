import { useState } from 'react'
import type { RegistryTool } from '../types'

interface Props {
  tool: RegistryTool
  index: number
}

const COMPLEXITY_LEVELS: Record<string, number> = {
  simple: 1,
  intermediate: 2,
  advanced: 3,
}

function ComplexityDots({ level }: { level: string }) {
  const filled = COMPLEXITY_LEVELS[level] ?? 1
  return (
    <span className="complexity-dots" title={level}>
      {[1, 2, 3].map((i) => (
        <span key={i} className={`dot ${i <= filled ? 'dot-filled' : ''}`} />
      ))}
    </span>
  )
}

export default function ToolCard({ tool, index }: Props) {
  const [copied, setCopied] = useState(false)
  const installCmd = `npx @yoavsb25/claude-tools install ${tool.name}`

  function copy() {
    navigator.clipboard.writeText(installCmd).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  const hasRequirements =
    (tool.requirements.platform && tool.requirements.platform !== 'any') ||
    tool.requirements.mcp_servers.length > 0 ||
    tool.requirements.python

  return (
    <article
      className="card"
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <div className="card-top">
        <div className="card-name-row">
          <span className="card-name">{tool.name}</span>
          <div className="card-badges">
            <span className={`badge badge-${tool.type}`}>{tool.type}</span>
            <ComplexityDots level={tool.complexity} />
          </div>
        </div>
        <div className="card-meta">
          <span className="meta-chip">{tool.category}</span>
          {tool.requirements.platform !== 'any' && (
            <span className="meta-chip meta-chip-dim">{tool.requirements.platform}</span>
          )}
        </div>
      </div>

      <p className="card-desc">{tool.description}</p>

      <div className="card-install">
        <code className="install-cmd">$ {installCmd}</code>
        <button
          className={`copy-btn ${copied ? 'copy-btn-success' : ''}`}
          onClick={copy}
          aria-label="Copy install command"
        >
          {copied ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          )}
        </button>
      </div>

      {hasRequirements && (
        <div className="card-reqs">
          {tool.requirements.platform !== 'any' && (
            <span className="req-item">⌘ {tool.requirements.platform} only</span>
          )}
          {tool.requirements.mcp_servers.map((mcp) => (
            <span key={mcp} className="req-item">↳ {mcp} MCP</span>
          ))}
          {tool.requirements.python && (
            <span className="req-item">⬡ python {tool.requirements.python}</span>
          )}
        </div>
      )}
    </article>
  )
}
