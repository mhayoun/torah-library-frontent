import React, { useState } from 'react'
import { Play, Clock, Eye, Calendar, X, ExternalLink, BookOpen } from 'lucide-react'

function formatDate(iso) {
  if (!iso) return null
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('he-IL', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch { return null }
}

function formatViews(n) {
  if (n == null) return null
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

export default function VideoCard({ video }) {
  const [modalOpen, setModalOpen] = useState(false)

  const thumb = video.thumbnail ||
    (video.id ? `https://img.youtube.com/vi/${video.id}/mqdefault.jpg` : null)

  return (
    <>
      <article style={styles.card} onClick={() => setModalOpen(true)}>
        {/* Thumbnail */}
        <div style={styles.thumbWrap}>
          {thumb
            ? <img src={thumb} alt={video.title} style={styles.thumb} loading="lazy" />
            : <div style={styles.thumbPlaceholder}><BookOpen size={32} color="#B8860B" /></div>
          }
          <div style={styles.playOverlay}>
            <div style={styles.playBtn}><Play size={20} fill="#F5F0E8" color="#F5F0E8" /></div>
          </div>
          {video.duration && video.duration !== 'Unknown' && (
            <span style={styles.durationBadge}>{video.duration}</span>
          )}
        </div>

        {/* Meta */}
        <div style={styles.body}>
          <div style={styles.topRow}>
            <div style={styles.category}>{video.category}</div>
            {video.hebraic_year && (
              <span style={styles.yearBadge}>{video.hebraic_year}</span>
            )}
          </div>
          <h3 style={styles.title}>{video.title}</h3>
          <div style={styles.playlist}>{video.playlist}</div>

          <div style={styles.meta}>
            {video.upload_date && (
              <span style={styles.metaItem}>
                <Calendar size={11} style={{ marginLeft: 3 }} />
                {formatDate(video.upload_date)}
              </span>
            )}
            {video.view_count != null && (
              <span style={styles.metaItem}>
                <Eye size={11} style={{ marginLeft: 3 }} />
                {formatViews(video.view_count)} צפיות
              </span>
            )}
          </div>
        </div>
      </article>

      {/* Modal */}
      {modalOpen && (
        <div style={styles.backdrop} onClick={() => setModalOpen(false)}>
          <div style={styles.modal} onClick={e => e.stopPropagation()}>
            <button style={styles.closeBtn} onClick={() => setModalOpen(false)}>
              <X size={20} />
            </button>
            <h2 style={styles.modalTitle}>{video.title}</h2>
            <div style={styles.categoryTag}>{video.category}</div>

            {/* YouTube embed */}
            {video.id && (
              <div style={styles.embedWrap}>
                <iframe
                  src={`https://www.youtube.com/embed/${video.id}?rel=0&hl=iw`}
                  title={video.title}
                  style={styles.embed}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            )}

            <div style={styles.modalMeta}>
              {video.hebraic_year && (
                <div style={styles.modalMetaItem}>
                  <BookOpen size={14} />
                  <span>{video.hebraic_year}</span>
                </div>
              )}
              {video.playlist && (
                <div style={styles.modalMetaItem}>
                  <BookOpen size={14} />
                  <span>{video.playlist}</span>
                </div>
              )}
              {video.upload_date && (
                <div style={styles.modalMetaItem}>
                  <Calendar size={14} />
                  <span>{formatDate(video.upload_date)}</span>
                </div>
              )}
              {video.duration && video.duration !== 'Unknown' && (
                <div style={styles.modalMetaItem}>
                  <Clock size={14} />
                  <span>{video.duration}</span>
                </div>
              )}
              {video.view_count != null && (
                <div style={styles.modalMetaItem}>
                  <Eye size={14} />
                  <span>{formatViews(video.view_count)} צפיות</span>
                </div>
              )}
            </div>

            <a href={video.url} target="_blank" rel="noopener noreferrer" style={styles.ytLink}>
              <ExternalLink size={14} style={{ marginLeft: 6 }} />
              פתח ביוטיוב
            </a>
          </div>
        </div>
      )}
    </>
  )
}

const styles = {
  card: {
    background: '#FDFBF7',
    borderRadius: 10,
    overflow: 'hidden',
    boxShadow: '0 2px 12px rgba(28,22,16,.08)',
    border: '1px solid rgba(184,134,11,.15)',
    cursor: 'pointer',
    transition: 'transform .2s, box-shadow .2s',
    display: 'flex',
    flexDirection: 'column',
  },
  thumbWrap: {
    position: 'relative',
    aspectRatio: '16/9',
    background: '#EAE2D0',
    overflow: 'hidden',
  },
  thumb: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    display: 'block',
  },
  thumbPlaceholder: {
    width: '100%',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#EAE2D0',
  },
  playOverlay: {
    position: 'absolute',
    inset: 0,
    background: 'rgba(14,36,64,.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    opacity: 0,
    transition: 'opacity .2s',
  },
  playBtn: {
    width: 48,
    height: 48,
    borderRadius: '50%',
    background: 'rgba(184,134,11,.9)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 12px rgba(0,0,0,.4)',
  },
  durationBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    background: 'rgba(14,36,64,.85)',
    color: '#F5F0E8',
    fontSize: '.72rem',
    padding: '2px 6px',
    borderRadius: 4,
    fontFamily: "'Heebo', sans-serif",
  },
  body: {
    padding: '14px 16px 16px',
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  category: {
    fontSize: '.68rem',
    fontWeight: 600,
    color: '#B8860B',
    letterSpacing: '.05em',
    textTransform: 'uppercase',
  },
  yearBadge: {
    fontSize: '.7rem',
    fontWeight: 600,
    color: '#1A3A5C',
    background: 'rgba(26,58,92,.1)',
    padding: '2px 8px',
    borderRadius: 20,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
  title: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '.95rem',
    fontWeight: 600,
    color: '#1C1610',
    lineHeight: 1.4,
    flex: 1,
  },
  playlist: {
    fontSize: '.75rem',
    color: '#6B5E47',
  },
  meta: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
    marginTop: 4,
  },
  metaItem: {
    display: 'flex',
    alignItems: 'center',
    fontSize: '.7rem',
    color: '#6B5E47',
  },
  backdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(14,36,64,.75)',
    backdropFilter: 'blur(4px)',
    zIndex: 999,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  modal: {
    background: '#FDFBF7',
    borderRadius: 16,
    padding: 28,
    maxWidth: 760,
    width: '100%',
    maxHeight: '90vh',
    overflowY: 'auto',
    position: 'relative',
    border: '1px solid rgba(184,134,11,.3)',
    boxShadow: '0 20px 60px rgba(0,0,0,.4)',
  },
  closeBtn: {
    position: 'absolute',
    top: 16,
    left: 16,
    background: 'rgba(184,134,11,.1)',
    border: '1px solid rgba(184,134,11,.3)',
    borderRadius: '50%',
    width: 36,
    height: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#1C1610',
    cursor: 'pointer',
  },
  modalTitle: {
    fontFamily: "'Frank Ruhl Libre', serif",
    fontSize: '1.25rem',
    fontWeight: 700,
    color: '#1C1610',
    marginBottom: 8,
    paddingLeft: 44,
  },
  categoryTag: {
    display: 'inline-block',
    background: 'rgba(184,134,11,.15)',
    color: '#8B6500',
    fontSize: '.72rem',
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 20,
    marginBottom: 16,
  },
  embedWrap: {
    position: 'relative',
    paddingBottom: '56.25%',
    height: 0,
    borderRadius: 10,
    overflow: 'hidden',
    marginBottom: 20,
    background: '#000',
  },
  embed: {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    border: 'none',
  },
  modalMeta: {
    display: 'flex',
    gap: 20,
    flexWrap: 'wrap',
    marginBottom: 20,
    padding: '14px 16px',
    background: '#F5F0E8',
    borderRadius: 8,
    border: '1px solid rgba(184,134,11,.15)',
  },
  modalMetaItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: '.8rem',
    color: '#3D3323',
  },
  ytLink: {
    display: 'inline-flex',
    alignItems: 'center',
    background: '#1A3A5C',
    color: '#F5F0E8',
    padding: '9px 20px',
    borderRadius: 6,
    fontSize: '.85rem',
    fontWeight: 500,
    fontFamily: "'Heebo', sans-serif",
    transition: 'background .15s',
  },
}
