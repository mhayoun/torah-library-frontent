import React from 'react'
import VideoCard from '../components/VideoCard.jsx'

export default function CategoryPage({ category, playlists: videos }) {
  // "playlists" prop name kept for App.jsx compatibility — it now holds a flat video array

  return (
    <div style={styles.page}>
      <div style={styles.catHeader}>
        <h2 style={styles.catTitle}>{category}</h2>
        <span style={styles.catMeta}>{videos.length} שיעורים</span>
        <div style={styles.ornament} />
      </div>

      {videos.length === 0
        ? <p style={styles.empty}>אין שיעורים בקטגוריה זו</p>
        : (
          <div style={styles.grid}>
            {videos.map(v => (
              <VideoCard key={v.id} video={{ ...v, category }} />
            ))}
          </div>
        )
      }
    </div>
  )
}

const styles = {
  page: { padding: '32px 0 60px' },
  catHeader: { marginBottom: 32 },
  catTitle: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '1.8rem',
    fontWeight: 900,
    color: '#1C1610',
    marginBottom: 6,
  },
  catMeta: { fontSize: '.8rem', color: '#6B5E47' },
  ornament: {
    marginTop: 14,
    height: 2,
    background: 'linear-gradient(to left, transparent, #B8860B 30%, #D4A017 50%, #B8860B 70%, transparent)',
    borderRadius: 2,
    maxWidth: 400,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
    gap: 16,
  },
  empty: {
    padding: '40px 0',
    color: '#6B5E47',
    fontSize: '.9rem',
    fontFamily: "'Heebo', sans-serif",
  },
}
