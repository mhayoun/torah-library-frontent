import React, { useState, useMemo } from 'react'
import { Search, Filter, SlidersHorizontal } from 'lucide-react'
import VideoCard from '../components/VideoCard.jsx'

const ALL_LABEL = 'כל הקטגוריות'
const ALL_YEARS = 'כל השנים'

export default function SearchPage({ allVideos, categories, years }) {
  const [query, setQuery]       = useState('')
  const [category, setCategory] = useState(ALL_LABEL)
  const [year, setYear]         = useState(ALL_YEARS)
  const [searched, setSearched] = useState(false)

  const results = useMemo(() => {
    if (!searched) return []
    return allVideos.filter(v => {
      const matchQuery = !query.trim() ||
        v.title.includes(query) ||
        v.playlist?.includes(query) ||
        v.category?.includes(query)
      const matchCat  = category === ALL_LABEL || v.category === category
      const matchYear = year === ALL_YEARS || (
        v.title.includes(year) ||
        (v.upload_date && new Date(v.upload_date).getFullYear() === Number(year))
      )
      return matchQuery && matchCat && matchYear
    })
  }, [allVideos, query, category, year, searched])

  const handleSearch = () => setSearched(true)

  const handleKey = (e) => { if (e.key === 'Enter') handleSearch() }

  return (
    <div style={styles.page}>
      {/* Search panel */}
      <div style={styles.panel}>
        <div style={styles.panelHeader}>
          <SlidersHorizontal size={18} color="#B8860B" />
          <span style={styles.panelTitle}>חיפוש שיעורים</span>
        </div>

        <div style={styles.controls}>
          {/* Text search */}
          <div style={styles.inputWrap}>
            <Search size={16} style={styles.inputIcon} />
            <input
              type="text"
              placeholder="חיפוש לפי כותרת…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKey}
              style={styles.input}
              dir="rtl"
            />
          </div>

          {/* Category select */}
          <div style={styles.selectWrap}>
            <Filter size={14} style={styles.selectIcon} />
            <select
              value={category}
              onChange={e => setCategory(e.target.value)}
              style={styles.select}
            >
              <option value={ALL_LABEL}>{ALL_LABEL}</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Year listbox */}
          <div style={styles.selectWrap}>
            <select
              value={year}
              onChange={e => setYear(e.target.value)}
              style={styles.select}
            >
              <option value={ALL_YEARS}>{ALL_YEARS}</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>

          <button style={styles.searchBtn} onClick={handleSearch}>
            <Search size={15} style={{ marginLeft: 6 }} />
            חפש
          </button>
        </div>
      </div>

      {/* Results */}
      {!searched && (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>🔍</div>
          <p style={styles.emptyText}>הגדירו פרמטרים לחיפוש ולחצו על "חפש"</p>
        </div>
      )}

      {searched && results.length === 0 && (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>📜</div>
          <p style={styles.emptyText}>לא נמצאו תוצאות. נסו מילות חיפוש אחרות.</p>
        </div>
      )}

      {results.length > 0 && (
        <>
          <div style={styles.resultsHeader}>
            <span style={styles.resultCount}>{results.length} שיעורים נמצאו</span>
          </div>
          <div style={styles.grid}>
            {results.map(v => <VideoCard key={v.id} video={v} />)}
          </div>
        </>
      )}
    </div>
  )
}

const styles = {
  page: { padding: '32px 0 60px' },
  panel: {
    background: '#FDFBF7',
    border: '1px solid rgba(184,134,11,.2)',
    borderRadius: 12,
    padding: '20px 24px',
    marginBottom: 32,
    boxShadow: '0 2px 12px rgba(28,22,16,.07)',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
  },
  panelTitle: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '1.05rem',
    fontWeight: 600,
    color: '#1C1610',
  },
  controls: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  inputWrap: {
    position: 'relative',
    flex: '1 1 240px',
  },
  inputIcon: {
    position: 'absolute',
    right: 12,
    top: '50%',
    transform: 'translateY(-50%)',
    color: '#6B5E47',
    pointerEvents: 'none',
  },
  input: {
    width: '100%',
    padding: '10px 38px 10px 14px',
    border: '1.5px solid #D4C5A0',
    borderRadius: 8,
    fontFamily: "'Heebo', sans-serif",
    fontSize: '.9rem',
    background: '#FDFBF7',
    color: '#1C1610',
    outline: 'none',
    direction: 'rtl',
  },
  selectWrap: {
    position: 'relative',
    flex: '0 1 180px',
  },
  selectIcon: {
    position: 'absolute',
    right: 10,
    top: '50%',
    transform: 'translateY(-50%)',
    color: '#6B5E47',
    pointerEvents: 'none',
  },
  select: {
    width: '100%',
    padding: '10px 32px 10px 14px',
    border: '1.5px solid #D4C5A0',
    borderRadius: 8,
    fontFamily: "'Heebo', sans-serif",
    fontSize: '.88rem',
    background: '#FDFBF7',
    color: '#1C1610',
    direction: 'rtl',
    appearance: 'none',
    cursor: 'pointer',
    outline: 'none',
  },
  searchBtn: {
    background: 'linear-gradient(135deg, #1A3A5C, #0E2440)',
    color: '#F5F0E8',
    border: 'none',
    borderRadius: 8,
    padding: '10px 24px',
    fontFamily: "'Heebo', sans-serif",
    fontSize: '.9rem',
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    whiteSpace: 'nowrap',
    boxShadow: '0 2px 8px rgba(14,36,64,.3)',
    flexShrink: 0,
  },
  empty: {
    textAlign: 'center',
    padding: '80px 24px',
    color: '#6B5E47',
  },
  emptyIcon: { fontSize: '3rem', marginBottom: 16 },
  emptyText: { fontSize: '1rem', fontFamily: "'Frank Ruhl Libre', serif" },
  resultsHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
    padding: '0 4px',
  },
  resultCount: {
    fontSize: '.85rem',
    color: '#6B5E47',
    fontFamily: "'Heebo', sans-serif",
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: 20,
  },
}
