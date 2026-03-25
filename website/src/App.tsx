import { useState, useEffect, useMemo } from 'react'
import type { Registry, RegistryTool } from './types'
import Header from './components/Header'
import FilterBar from './components/FilterBar'
import ToolCard from './components/ToolCard'

const REGISTRY_URL =
  'https://raw.githubusercontent.com/Yoavsb25/claude-code-tools/main/registry.json'

export default function App() {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [error, setError] = useState(false)
  const [category, setCategory] = useState('all')
  const [complexity, setComplexity] = useState('all')

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10_000)

    fetch(REGISTRY_URL, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: unknown) => {
        if (
          typeof data !== 'object' ||
          data === null ||
          !Array.isArray((data as Record<string, unknown>).tools)
        ) {
          throw new Error('Invalid registry shape')
        }
        setRegistry(data as Registry)
      })
      .catch(() => setError(true))
      .finally(() => clearTimeout(timeoutId))

    return () => {
      clearTimeout(timeoutId)
      controller.abort()
    }
  }, [])

  const categories = useMemo(() => {
    if (!registry) return []
    return ['all', ...Array.from(new Set(registry.tools.map((t) => t.category))).sort()]
  }, [registry])

  const filtered = useMemo<RegistryTool[]>(() => {
    if (!registry) return []
    return registry.tools.filter((t) => {
      const catMatch = category === 'all' || t.category === category
      const cmpMatch = complexity === 'all' || t.complexity === complexity
      return catMatch && cmpMatch
    })
  }, [registry, category, complexity])

  return (
    <div className="app">
      <Header />
      <main className="main">
        {error && (
          <p className="error">Failed to load registry. Check your connection and refresh.</p>
        )}
        {!registry && !error && (
          <p className="loading">Loading registry<span className="blink">_</span></p>
        )}
        {registry && (
          <>
            <FilterBar
              categories={categories}
              category={category}
              complexity={complexity}
              onCategory={setCategory}
              onComplexity={setComplexity}
              count={filtered.length}
              total={registry.count}
            />
            <div className="grid">
              {filtered.map((tool, i) => (
                <ToolCard key={tool.name} tool={tool} index={i} />
              ))}
            </div>
          </>
        )}
      </main>
      <footer className="footer">
        <span>MIT License · <a href="https://github.com/Yoavsb25/claude-code-tools" target="_blank" rel="noopener noreferrer">github.com/Yoavsb25/claude-code-tools</a></span>
      </footer>
    </div>
  )
}
