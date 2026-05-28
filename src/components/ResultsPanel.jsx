import React from 'react';

/* ── Download Helpers ─────────────────────────────────────────────── */

/** Download a plain-text string as a .txt file */
function downloadTextFile(content, filename) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  triggerDownload(blob, filename);
}

/** Download a base64 data-URI as an image file */
function downloadBase64Image(dataUri, filename) {
  const byteString = atob(dataUri.split(',')[1]);
  const mimeType = dataUri.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  const blob = new Blob([ab], { type: mimeType });
  triggerDownload(blob, filename);
}

/** Create a temporary link and click it to start download */
function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ── Download Button Component ────────────────────────────────────── */
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
  if (!entities || entities.total_entities === 0) {
    return <span style={{ color: 'var(--text-muted)' }}>No PII detected.</span>;
  }

  return (
    <div style={{ marginBottom: '1.5rem' }}>
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

/* ── Main Results Panel ───────────────────────────────────────────── */
export default function ResultsPanel({ result, activeTab }) {
  if (!result) return null;

  return (
    <div className="glass-card" style={{ marginTop: '2rem', animation: 'fadeIn 0.5s ease' }}>
      <h2 style={{ marginBottom: '1.5rem', color: 'white' }}>Analysis Results</h2>

      {/* Entities Badges */}
      <EntitiesBadges entities={result.entities} />

      {/* TEXT TAB RESULTS */}
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
            <DownloadBtn onClick={() => downloadTextFile(result.original, 'original_text.txt')}>
              Original Text
            </DownloadBtn>
            <DownloadBtn onClick={() => downloadTextFile(result.sanitized, 'sanitized_text.txt')}>
              Sanitized Text
            </DownloadBtn>
          </div>
        </>
      )}

      {/* IMAGE TAB RESULTS */}
      {activeTab === 'image' && (
        <>
          <div className="results-grid">
            <div className="result-box">
              <h3>Original Image</h3>
              {result.original_image_base64 && (
                <img src={result.original_image_base64} alt="Original" className="image-preview" />
              )}
              <h4 style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Extracted Text:</h4>
              <div className="text-preview">{result.original_text || 'No text'}</div>
            </div>
            <div className="result-box">
              <h3>Masked Image</h3>
              {result.redacted_image_base64 && (
                <img src={result.redacted_image_base64} alt="Redacted" className="image-preview" style={{ borderColor: '#ef4444' }} />
              )}
              <h4 style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Sanitized Text:</h4>
              <div className="text-preview" style={{ color: '#a78bfa' }}>{result.sanitized_text || 'No text'}</div>
            </div>
          </div>
          <div className="download-bar">
            {result.original_image_base64 && (
              <DownloadBtn onClick={() => downloadBase64Image(result.original_image_base64, 'original_image.png')}>
                Original Image
              </DownloadBtn>
            )}
            {result.redacted_image_base64 && (
              <DownloadBtn onClick={() => downloadBase64Image(result.redacted_image_base64, 'redacted_image.png')}>
                Redacted Image
              </DownloadBtn>
            )}
            <DownloadBtn onClick={() => downloadTextFile(result.sanitized_text || '', 'sanitized_text.txt')}>
              Sanitized Text
            </DownloadBtn>
          </div>
        </>
      )}

      {/* PDF TAB RESULTS */}
      {activeTab === 'pdf' && result.pages && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {result.pages.map((p, idx) => (
              <div key={idx}>
                {/* Page header */}
                <div className="result-box" style={{ gridColumn: '1 / -1', background: 'rgba(0,0,0,0.4)', textAlign: 'center', marginBottom: '1rem' }}>
                  <h2 style={{ color: 'white' }}>
                    Page {p.page_number} ({p.extraction_method || 'Unknown'})
                  </h2>
                </div>

                {/* Image-based view (preferred) */}
                {p.original_image_base64 && p.redacted_image_base64 ? (
                  <div className="results-grid">
                    <div className="result-box">
                      <h3>Original PDF Page</h3>
                      <img src={p.original_image_base64} alt="Original" className="image-preview" />
                      <div className="text-preview" style={{ marginTop: '1rem' }}>
                        {p.original_text || ''}
                      </div>
                    </div>
                    <div className="result-box">
                      <h3>Redacted PDF Page</h3>
                      <img src={p.redacted_image_base64} alt="Redacted" className="image-preview" style={{ borderColor: '#ef4444' }} />
                      <div className="text-preview" style={{ marginTop: '1rem', color: '#a78bfa' }}>
                        {p.sanitized_text || ''}
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Text-only fallback */
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
            <DownloadBtn onClick={() => downloadTextFile(result.combined_original_text || '', 'original_full_text.txt')}>
              Full Original Text
            </DownloadBtn>
            <DownloadBtn onClick={() => downloadTextFile(result.combined_sanitized_text || '', 'sanitized_full_text.txt')}>
              Full Sanitized Text
            </DownloadBtn>
            {/* Per-page image downloads for scanned PDFs */}
            {result.pages.some(p => p.redacted_image_base64) && (
              <DownloadBtn onClick={() => {
                result.pages.forEach((p, i) => {
                  if (p.redacted_image_base64) {
                    downloadBase64Image(p.redacted_image_base64, `redacted_page_${p.page_number}.png`);
                  }
                });
              }}>
                All Redacted Pages
              </DownloadBtn>
            )}
          </div>
        </>
      )}
    </div>
  );
}
