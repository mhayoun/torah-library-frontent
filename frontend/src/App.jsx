import React, { useState } from 'react'
import Header from './components/Header.jsx'
import HomePage from './pages/HomePage.jsx'
import CategoryPage from './pages/CategoryPage.jsx'
import SearchPage from './pages/SearchPage.jsx'
import { useVideos } from './hooks/useVideos.js'

export default function App() {
  const { catalog, allVideos, categories, years, loading, error } = useVideos()
  const [activeTab, setActiveTab] = useState('כל הקטגוריות')

  const handleTabChange = (tab) => setActiveTab(tab)

  const renderContent = () => {
    if (loading) return (
      <div style={styles.center}>
        <div style={styles.spinner} />
        <p style={styles.loadingText}>טוען את מאגר השיעורים…</p>
      </div>
    )
    if (error) return (
      <div style={styles.center}>
        <p style={styles.errorText}>שגיאה: {error}</p>
        <p style={styles.errorSub}>ודאו שהקובץ categorized_videos.json קיים בתיקיית public</p>
      </div>
    )
    if (!catalog) return null

    if (activeTab === '__search__') {
      return <SearchPage allVideos={allVideos} categories={categories} years={years} />
    }
    if (activeTab === 'כל הקטגוריות') {
      return <HomePage catalog={catalog} onCategorySelect={handleTabChange} />
    }
    // Specific category — catalog[tab] is now a flat video array
    const videos = catalog[activeTab]
    if (!videos) return (
      <div style={styles.center}><p style={styles.errorText}>קטגוריה לא נמצאה</p></div>
    )
    return <CategoryPage category={activeTab} playlists={videos} />
  }

  return (
    <div>
      <Header activeTab={activeTab} onTabChange={handleTabChange} />
      <main style={styles.main}>
        <div style={styles.container}>
          {renderContent()}
        </div>
      </main>
      <footer style={styles.footer}>
        <div style={styles.footerInner}>
          <span>מאגר שיעורי תורה</span>
          <span style={styles.footerDot}>•</span>
          <span>כל הזכויות שמורות</span>
        </div>
      </footer>
    </div>
  )
}

const styles = {
  main: { minHeight: 'calc(100vh - 68px - 56px)' },
  container: { maxWidth: 1200, margin: '0 auto', padding: '0 24px' },
  center: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 400,
    gap: 12,
    textAlign: 'center',
  },
  spinner: {
    width: 44,
    height: 44,
    border: '3px solid rgba(184,134,11,.2)',
    borderTop: '3px solid #B8860B',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  loadingText: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '1rem',
    color: '#6B5E47',
  },
  errorText: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '1.1rem',
    color: '#8B1A1A',
  },
  errorSub: { fontSize: '.85rem', color: '#6B5E47' },
  footer: {
    background: '#1C1610',
    padding: '16px 24px',
    marginTop: 40,
  },
  footerInner: {
    maxWidth: 1200,
    margin: '0 auto',
    display: 'flex',
    gap: 12,
    justifyContent: 'center',
    color: 'rgba(245,240,232,.4)',
    fontSize: '.78rem',
    fontFamily: "'Heebo', sans-serif",
  },
  footerDot: { opacity: .3 },
}
