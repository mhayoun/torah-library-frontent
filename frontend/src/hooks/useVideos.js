import { useState, useEffect, useMemo } from 'react'

export function useVideos() {
  const [catalog, setCatalog] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    fetch('/categorized_videos.json')
      .then(r => { if (!r.ok) throw new Error('Failed to load data'); return r.json() })
      .then(data => { setCatalog(data); setLoading(false) })
      .catch(e  => { setError(e.message); setLoading(false) })
  }, [])

  /** Flat list of all videos with their category injected */
  const allVideos = useMemo(() => {
    if (!catalog) return []
    return Object.entries(catalog).flatMap(([category, videos]) =>
      videos.map(v => ({ ...v, category }))
    )
  }, [catalog])

  /** All unique years parsed from video titles */
  const years = useMemo(() => {
    const hebrewYearRe = /תש[פצ](?:\"[א-ת]|[׳']?[א-ת]?)/g
    const yearSet = new Set()

    allVideos.forEach(v => {
      // Gregorian
      const gm = v.title.match(/\b(20\d{2})\b/)
      if (gm) yearSet.add(gm[1])

      // Hebrew year labels like תשפ"ה תשפ"ד תשצ"א
      const hm = v.title.match(hebrewYearRe)
      if (hm) hm.forEach(y => yearSet.add(y))

      // Also try upload_date year
      if (v.upload_date) {
        const uy = new Date(v.upload_date).getFullYear()
        if (!isNaN(uy)) yearSet.add(String(uy))
      }
    })

    return Array.from(yearSet).sort().reverse()
  }, [allVideos])

  const categories = catalog ? Object.keys(catalog) : []

  return { catalog, allVideos, categories, years, loading, error }
}
