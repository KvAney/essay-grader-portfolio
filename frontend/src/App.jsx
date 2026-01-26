import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [file, setFile] = useState(null);
  const [submissionId, setSubmissionId] = useState(null);
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) {
      alert('Please select a file');
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API_BASE_URL}/upload/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSubmissionId(response.data.submission_id);
      setStatus(response.data.status);
      setResult(null);
    } catch (error) {
      alert('Upload failed: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCheckStatus = async () => {
    if (!submissionId) {
      alert('No submission to check');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/status/${submissionId}`);
      setStatus(response.data.status);
      if (response.data.result) {
        setResult(response.data.result);
      }
    } catch (error) {
      alert('Status check failed: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Essay Grader</h1>
        <p>Upload your essay for AI-powered evaluation</p>
      </header>

      <div className="container">
        <div className="upload-section">
          <h2>Upload Essay</h2>
          <input
            type="file"
            onChange={handleFileChange}
            accept=".pdf,.txt,.docx"
            disabled={loading}
          />
          <button onClick={handleUpload} disabled={loading || !file}>
            {loading ? 'Uploading...' : 'Upload'}
          </button>
        </div>

        {submissionId && (
          <div className="status-section">
            <h2>Submission #{submissionId}</h2>
            <p>Status: <strong>{status}</strong></p>
            <button onClick={handleCheckStatus} disabled={loading}>
              {loading ? 'Checking...' : 'Check Status'}
            </button>
          </div>
        )}

        {result && (
          <div className="result-section">
            <h2>Evaluation Result</h2>
            <div className="result-box">
              {result}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
