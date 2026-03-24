interface Props {
  categories: string[]
  category: string
  complexity: string
  onCategory: (v: string) => void
  onComplexity: (v: string) => void
  count: number
  total: number
}

const COMPLEXITIES = ['all', 'simple', 'intermediate', 'advanced']

export default function FilterBar({
  categories,
  category,
  complexity,
  onCategory,
  onComplexity,
  count,
  total,
}: Props) {
  return (
    <div className="filters">
      <div className="filter-row">
        <span className="filter-label">category</span>
        <div className="filter-chips">
          {categories.map((c) => (
            <button
              key={c}
              className={`chip ${category === c ? 'chip-active' : ''}`}
              onClick={() => onCategory(c)}
            >
              [{c}]
            </button>
          ))}
        </div>
      </div>
      <div className="filter-row">
        <span className="filter-label">complexity</span>
        <div className="filter-chips">
          {COMPLEXITIES.map((c) => (
            <button
              key={c}
              className={`chip ${complexity === c ? 'chip-active' : ''}`}
              onClick={() => onComplexity(c)}
            >
              [{c}]
            </button>
          ))}
        </div>
      </div>
      <div className="filter-count">
        {count === total ? (
          <span>{total} tools</span>
        ) : (
          <span>{count} of {total} tools</span>
        )}
      </div>
    </div>
  )
}
