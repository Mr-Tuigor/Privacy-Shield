import React, { useState } from 'react';
import TextInputPanel from './components/TextInputPanel';
import ImageInputPanel from './components/ImageInputPanel';
import PdfInputPanel from './components/PdfInputPanel';
import ResultsPanel from './components/ResultsPanel';

function App() {
  const [activeTab, setActiveTab] = useState('text');
  const [resultData, setResultData] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setResultData(null);
    setErrorMsg('');
  };

  const handleResult = (data) => {
    setErrorMsg('');
    setResultData(data);
  };

  const handleError = (msg) => {
    setResultData(null);
    setErrorMsg(msg);
  };

  return (
    <div className="container">
      <h1>Privacy Shield</h1>
      <p className="subtitle">AI-Powered PII Redaction Engine</p>

      {/* TABS */}
      <div className="tabs">
        <button 
          className={`tab-btn ${activeTab === 'text' ? 'active' : ''}`}
          onClick={() => handleTabChange('text')}
        >
          Raw Text
        </button>
        <button 
          className={`tab-btn ${activeTab === 'image' ? 'active' : ''}`}
          onClick={() => handleTabChange('image')}
        >
          Image Scan
        </button>
        <button 
          className={`tab-btn ${activeTab === 'pdf' ? 'active' : ''}`}
          onClick={() => handleTabChange('pdf')}
        >
          PDF Document
        </button>
      </div>

      {errorMsg && (
        <div style={{ color: 'var(--danger)', marginBottom: '1rem', textAlign: 'center', fontWeight: '600' }}>
          Error: {errorMsg}
        </div>
      )}

      {/* INPUT PANELS */}
      <div className="glass-card">
        {activeTab === 'text' && <TextInputPanel onResult={handleResult} onError={handleError} />}
        {activeTab === 'image' && <ImageInputPanel onResult={handleResult} onError={handleError} />}
        {activeTab === 'pdf' && <PdfInputPanel onResult={handleResult} onError={handleError} />}
      </div>

      {/* RESULTS PANEL */}
      <ResultsPanel result={resultData} activeTab={activeTab} />

    </div>
  );
}

export default App;