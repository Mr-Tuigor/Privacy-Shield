import { useState } from 'react';

function App() {
  const [inputText, setInputText] = useState('');
  const [outputText, setOutputText] = useState('');

  const handleScrub = async () => {
    // Call the C++ engine via the Electron bridge we set up in preload.js
    const result = await window.electronAPI.scrubText(inputText);
    setOutputText(result);
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h2>Privacy Shield (Core Test)</h2>
      
      <div style={{ marginBottom: '10px' }}>
        <textarea 
          rows="4" 
          cols="50" 
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Enter a prompt containing the name 'Amit'..."
        />
      </div>

      <button onClick={handleScrub} style={{ padding: '10px', cursor: 'pointer' }}>
        Scrub PII
      </button>

      <div style={{ marginTop: '20px', padding: '10px', backgroundColor: '#f0f0f0' }}>
        <strong>Sanitized Output:</strong>
        <p>{outputText || "Waiting for input..."}</p>
      </div>
    </div>
  );
}

export default App;