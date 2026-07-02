import { useState, useEffect, useMemo } from 'react'

const API_URL  = '/api/cours'
const STALE_MS = 6 * 60 * 60 * 1000  // 6h — same TTL as Redis

// ── Session cache (survives page navigation, cleared on tab close) ─────────
function getCached() {
  try {
    const raw = sessionStorage.getItem('cours_cache')
    if (!raw) return null
    const { data, ts } = JSON.parse(raw)
    if (Date.now() - ts > STALE_MS) return null
    return data
  } catch { return null }
}

function setCache(data) {
  try {
    sessionStorage.setItem('cours_cache', JSON.stringify({ data, ts: Date.now() }))
  } catch {}
}

// ── Hook ──────────────────────────────────────────────────────────────────
export function useVideos() {
  const [catalog,  setCatalog]  = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [lastSync, setLastSync] = useState(null)
  const [total,    setTotal]    = useState(0)
  const [newCount, setNewCount] = useState(0)

  useEffect(() => {
    // 1. Try session cache first — instant response
    const cached = getCached()
    if (cached) {
      setCatalog(cached.catalog)
      setLastSync(cached.last_sync)
      setTotal(cached.total  ?? 0)
      setNewCount(cached.new ?? 0)
      setLoading(false)
      return
    }

    // 2. Otherwise hit the API backend
    fetch(API_URL)
      .then(r => {
        if (!r.ok) throw new Error(`Erreur serveur : ${r.status}`)
        return r.json()
      })
      .then(data => {
        // Backend returns { catalog, total, new, last_sync }
        setCatalog(data.catalog)
        setLastSync(data.last_sync)
        setTotal(data.total  ?? 0)
        setNewCount(data.new ?? 0)
        setCache(data)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  // Flat list of all videos with their category injected
  const allVideos = useMemo(() => {
    if (!catalog) return []
    return Object.entries(catalog).flatMap(([category, videos]) =>
      videos.map(v => ({ ...v, category }))
    )
  }, [catalog])

  // Gematria value of each Hebrew letter — used only to sort hebraic_year
  // values chronologically (newest first). Final-letter forms map to the
  // same value as their regular counterpart.
  const GEMATRIA = {
    'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5, 'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9,
    'י': 10, 'כ': 20, 'ל': 30, 'מ': 40, 'נ': 50, 'ס': 60, 'ע': 70, 'פ': 80, 'צ': 90,
    'ק': 100, 'ר': 200, 'ש': 300, 'ת': 400,
    'ך': 20, 'ם': 40, 'ן': 50, 'ף': 80, 'ץ': 90,
  }
  const hebraicYearValue = (y) =>
    Array.from(y).reduce((sum, ch) => sum + (GEMATRIA[ch] || 0), 0)

  // All distinct hebraic_year values present across the videos, as supplied
  // directly by the backend (extract_hebraic_year) — newest year first.
  const years = useMemo(() => {
    const yearSet = new Set()
    allVideos.forEach(v => {
      if (v.hebraic_year) yearSet.add(v.hebraic_year)
    })
    return Array.from(yearSet).sort((a, b) => hebraicYearValue(b) - hebraicYearValue(a))
  }, [allVideos])

  const categories = catalog ? Object.keys(catalog) : []

  return { catalog, allVideos, categories, years, loading, error, lastSync, total, newCount }
}
