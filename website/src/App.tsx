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
    fetch(REGISTRY_URL)
      .then((r) => r.json())
      .then((data: Registry) => setRegistry(data))
      .catch(() => setError(true))
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
