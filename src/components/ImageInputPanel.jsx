import React, { useState, useRef } from 'react';
import { redactImageApi } from '../utils/api';

export default function ImageInputPanel({ onResult, onError }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleRedact = async () => {
    if (!file) return;
    
    setLoading(true);
    try {
      const data = await redactImageApi(file);
      onResult(data);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tab-content active" id="img-tab">
      <div>
        <label>Upload Image (PNG/JPG)</label>
        <input 
          type="file" 
          accept="image/*" 
          ref={fileInputRef}
          onChange={handleFileChange}
        />
      </div>
      <button 
        className="submit-btn" 
        onClick={handleRedact} 
        disabled={loading || !file}
      >
        <span>Redact Image</span>
        {loading && <div className="spinner"></div>}
      </button>
    </div>
  );
}
