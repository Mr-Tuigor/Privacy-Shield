import React, { useState } from 'react';
import { scrubTextApi } from '../utils/api';

export default function TextInputPanel({ onResult, onError }) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);

  const handleScrub = async () => {
    if (!text.trim()) return;
    
    setLoading(true);
    try {
      const data = await scrubTextApi(text);
      onResult(data);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tab-content active" id="text-tab">
      <div>
        <label>Enter Text Content</label>
        <textarea
          rows="6"
          placeholder="Paste some text containing sensitive information..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        ></textarea>
      </div>
      <button 
        className="submit-btn" 
        onClick={handleScrub} 
        disabled={loading || !text.trim()}
      >
        <span>Scrub Text Payload</span>
        {loading && <div className="spinner"></div>}
      </button>
    </div>
  );
}
