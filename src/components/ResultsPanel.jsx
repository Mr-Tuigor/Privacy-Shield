import React, { useState, useCallback } from 'react';

const API_BASE = 'http://localhost:8000/api';

/* ── Download Helpers ─────────────────────────────────────────────── */
function downloadTextFile(content, filename) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  triggerDownload(blob, filename);
}
function downloadBase64Image(dataUri, filename) {
  const byteString = atob(dataUri.split(',')[1]);
  const mimeType = dataUri.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
  triggerDownload(new Blob([ab], { type: mimeType }), filename);
}
function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

/* ── Download Button ──────────────────────────────────────────────── */
function DownloadBtn({ onClick, children }) {
  return (
    <button className="download-btn" onClick={onClick} title="Download">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      <span>{children}</span>
    </button>
  );
}

/* ── Entity Badges ────────────────────────────────────────────────── */
function EntitiesBadges({ entities }) {
  if (!entities || entities.total_entities === 0)
    return <span style={{ color: 'var(--text-muted)' }}>No PII detected.</span>;
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <p style={{ marginBottom: '0.5rem' }}>
        Found <strong>{entities.total_entities}</strong> sensitive items:
      </p>
      <div className="entities-container">
        {Object.entries(entities.by_type).map(([type, count]) => (
          <span key={type} className="entity-badge">
            <span className="entity-type">{type}:</span>
            <span className="entity-value">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── Redacted Words Panel ─────────────────────────────────────────── */
function RedactedWordsPanel({ piiMap }) {
  const [selected, setSelected] = useState(new Set());
  const [feedback, setFeedback] = useState(null); // { msg, color }

  const entries = Object.entries(piiMap || {});

  const showFeedback = (msg, color) => {
    setFeedback({ msg, color });
    setTimeout(() => setFeedback(null), 5000);
  };

  const togglePill = useCallback((token) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(token) ? next.delete(token) : next.add(token);
      return next;
    });
  }, []);

  const selectAll   = () => setSelected(new Set(entries.map(([t]) => t)));
  const deselectAll = () => setSelected(new Set());

  const postIgnore = async (words) => {
    try {
      const res = await fetch(`${API_BASE}/add-to-ignore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');
      const added = data.added.length;
      const skipped = data.skipped_duplicates;
      let msg = `✓ Added ${added} word(s) to ignore list.`;
      if (skipped > 0) msg += ` (${skipped} already existed — skipped)`;
      showFeedback(msg, 'var(--success)');
    } catch (e) {
      showFeedback('✗ Failed: ' + e.message, 'var(--danger)');
    }
  };

  const sendSelected = () => {
    const words = [...selected].map(t => piiMap[t]).filter(Boolean);
    if (!words.length) { showFeedback('⚠ No words selected. Click words to select them first.', 'var(--warning)'); return; }
    const ok = window.confirm(
      `Are you sure you want to add these ${words.length} word(s) to the ignore list?\n\n` +
      words.map(w => `• ${w}`).join('\n') +
      '\n\nThey will never be redacted in future scans.'
    );
    if (ok) postIgnore(words);
  };

  const sendAll = () => {
    const words = entries.map(([, v]) => v);
    if (!words.length) return;
    const ok = window.confirm(
      `⚠ WORST CASE: Are you absolutely sure you want to add ALL ${words.length} redacted word(s) to the ignore list?\n\n` +
      words.map(w => `• ${w}`).join('\n') +
      '\n\nThis will permanently prevent ALL of these from being redacted in future. This cannot be undone easily.'
    );
    if (ok) postIgnore(words);
  };

  return (
    <div className="redacted-panel">
      {/* Header row */}
      <div className="redacted-panel-header">
        <div className="redacted-panel-title">
          🔒 Redacted Words
          <span className="pill-count-badge">{entries.length}</span>
        </div>
        <div className="redacted-panel-actions">
          <button className="rp-btn rp-select"   onClick={selectAll}>Select All</button>
          <button className="rp-btn rp-deselect" onClick={deselectAll}>Deselect All</button>
          <button className="rp-btn rp-send"     onClick={sendSelected}>Add Selected to Ignore</button>
          <button className="rp-btn rp-all"      onClick={sendAll}>Add All (worst case)</button>
        </div>
      </div>

      {/* Scrollable pill area */}
      <div className="redacted-words-scroll">
        {entries.length === 0 ? (
          <span className="rp-empty">No redacted words detected.</span>
        ) : (
          entries
            .slice()
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([token, original]) => {
              const typeMatch = token.match(/^\[([A-Z_]+)_\d+\]$/);
              const typeLabel = typeMatch ? typeMatch[1] : 'PII';
              const isSelected = selected.has(token);
              return (
                <span
                  key={token}
                  className={`word-pill${isSelected ? ' selected' : ''}`}
                  onClick={() => togglePill(token)}
                  title={`Token: ${token}`}
                >
                  <span className="pill-check">{isSelected ? '✓' : '○'}</span>
                  <span className="pill-text">{original}</span>
                  <span className="pill-type">{typeLabel}</span>
                </span>
              );
            })
        )}
      </div>

      {/* Feedback line */}
      {feedback && (
        <p className="rp-feedback" style={{ color: feedback.color }}>
          {feedback.msg}
        </p>
      )}
    </div>
  );
}

/* ── Main Results Panel ───────────────────────────────────────────── */
export default function ResultsPanel({ result, activeTab }) {
  if (!result) return null;

  const piiMap = result.pii_map || {};

  return (
    <div className="glass-card" style={{ marginTop: '2rem', animation: 'fadeIn 0.5s ease' }}>
      <h2 style={{ marginBottom: '1.5rem', color: 'white' }}>Analysis Results</h2>

      {/* Redacted Words Panel — always at top */}
      <RedactedWordsPanel piiMap={piiMap} />

      {/* Entity summary badges */}
      <div style={{ marginBottom: '1.5rem' }}>
        <EntitiesBadges entities={result.entities} />
      </div>

      {/* TEXT TAB */}
      {activeTab === 'text' && (
        <>
          <div className="results-grid">
            <div className="result-box">
              <h3>Original text</h3>
              <div className="text-preview">{result.original}</div>
            </div>
            <div className="result-box">
              <h3>Sanitized text</h3>
              <div className="text-preview" style={{ color: '#a78bfa' }}>{result.sanitized}</div>
            </div>
          </div>
          <div className="download-bar">
            <DownloadBtn onClick={() => downloadTextFile(result.original,  'original_text.txt')}>Original Text</DownloadBtn>
            <DownloadBtn onClick={() => downloadTextFile(result.sanitized, 'sanitized_text.txt')}>Sanitized Text</DownloadBtn>
          </div>
        </>
      )}

      {/* IMAGE TAB */}
      {activeTab === 'image' && (
        <>
          <div className="results-grid">
            <div className="result-box">
              <h3>Original Image</h3>
              {result.original_image_base64 && <img src={result.original_image_base64} alt="Original" className="image-preview" />}
              <h4 style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Extracted Text:</h4>
              <div className="text-preview">{result.original_text || 'No text'}</div>
            </div>
            <div className="result-box">
              <h3>Masked Image</h3>
              {result.redacted_image_base64 && <img src={result.redacted_image_base64} alt="Redacted" className="image-preview" style={{ borderColor: '#ef4444' }} />}
              <h4 style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Sanitized Text:</h4>
              <div className="text-preview" style={{ color: '#a78bfa' }}>{result.sanitized_text || 'No text'}</div>
            </div>
          </div>
          <div className="download-bar">
            {result.original_image_base64 && <DownloadBtn onClick={() => downloadBase64Image(result.original_image_base64, 'original_image.png')}>Original Image</DownloadBtn>}
            {result.redacted_image_base64 && <DownloadBtn onClick={() => downloadBase64Image(result.redacted_image_base64, 'redacted_image.png')}>Redacted Image</DownloadBtn>}
            <DownloadBtn onClick={() => downloadTextFile(result.sanitized_text || '', 'sanitized_text.txt')}>Sanitized Text</DownloadBtn>
          </div>
        </>
      )}

      {/* PDF TAB */}
      {activeTab === 'pdf' && result.pages && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {result.pages.map((p, idx) => (
              <div key={idx}>
                <div className="result-box" style={{ background: 'rgba(0,0,0,0.4)', textAlign: 'center', marginBottom: '1rem' }}>
                  <h2 style={{ color: 'white' }}>Page {p.page_number} ({p.extraction_method || 'Unknown'})</h2>
                </div>
                {p.original_image_base64 && p.redacted_image_base64 ? (
                  <div className="results-grid">
                    <div className="result-box">
                      <h3>Original PDF Page</h3>
                      <img src={p.original_image_base64} alt="Original" className="image-preview" />
                      <div className="text-preview" style={{ marginTop: '1rem' }}>{p.original_text || ''}</div>
                    </div>
                    <div className="result-box">
                      <h3>Redacted PDF Page</h3>
                      <img src={p.redacted_image_base64} alt="Redacted" className="image-preview" style={{ borderColor: '#ef4444' }} />
                      <div className="text-preview" style={{ marginTop: '1rem', color: '#a78bfa' }}>{p.sanitized_text || ''}</div>
                    </div>
                  </div>
                ) : (
                  <div className="results-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                    <div className="result-box">
                      <h3>Original Text</h3>
                      <div className="text-preview">{p.original_text}</div>
                    </div>
                    <div className="result-box">
                      <h3>Masked Text</h3>
                      <div className="text-preview" style={{ color: '#a78bfa' }}>{p.sanitized_text}</div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="download-bar">
            <DownloadBtn onClick={() => downloadTextFile(result.combined_original_text  || '', 'original_full_text.txt')}>Full Original Text</DownloadBtn>
            <DownloadBtn onClick={() => downloadTextFile(result.combined_sanitized_text || '', 'sanitized_full_text.txt')}>Full Sanitized Text</DownloadBtn>
            {result.pages.some(p => p.redacted_image_base64) && (
              <DownloadBtn onClick={() => result.pages.forEach((p) => { if (p.redacted_image_base64) downloadBase64Image(p.redacted_image_base64, `redacted_page_${p.page_number}.png`); })}>
                All Redacted Pages
              </DownloadBtn>
            )}
          </div>
        </>
      )}
    </div>
  );
}
