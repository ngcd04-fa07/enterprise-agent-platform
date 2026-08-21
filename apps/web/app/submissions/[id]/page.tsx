"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface Submission {
  id: string;
  title: string;
  status: string;
}

interface DocumentItem {
  id: string;
  filename: string;
  status: "uploaded" | "processing" | "ready" | "failed";
  size_bytes: number;
}

interface SearchResult {
  chunk_id: string;
  document_id: string;
  page_number: number;
  text: string;
  score: number;
}

interface SearchResponse {
  results: SearchResult[];
  strategy: string;
  latency_ms: number;
}

export default function SubmissionDetailPage() {
  const params = useParams<{ id: string }>();
  const submissionId = params.id;
  const router = useRouter();
  const { user, loading, csrfToken } = useAuth();

  const [submission, setSubmission] = useState<Submission | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const loadSubmission = useCallback(async () => {
    const data = await api.get<Submission>(`/submissions/${submissionId}`);
    setSubmission(data);
  }, [submissionId]);

  const loadDocuments = useCallback(async () => {
    const data = await api.get<DocumentItem[]>(`/submissions/${submissionId}/documents`);
    setDocuments(data);
  }, [submissionId]);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (user) {
      void loadSubmission();
      void loadDocuments();
    }
  }, [user, loadSubmission, loadDocuments]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csrfToken || !fileInputRef.current?.files?.[0]) return;
    setUploadError(null);
    setUploading(true);
    try {
      await api.upload(
        `/submissions/${submissionId}/documents`,
        fileInputRef.current.files[0],
        csrfToken,
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadDocuments();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearchError(null);
    setSearching(true);
    try {
      const data = await api.post<SearchResponse>(`/submissions/${submissionId}/search`, {
        query,
      });
      setSearchResults(data);
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading...</p>
      </main>
    );
  }

  return (
    <main className="wide">
      <div className="page-header">
        <h1>{submission?.title ?? "Submission"}</h1>
        {submission && <span className="status-badge">{submission.status}</span>}
      </div>

      <section className="card">
        <h2>Documents</h2>
        <form onSubmit={handleUpload}>
          <label>
            Upload a PDF
            <input ref={fileInputRef} type="file" accept="application/pdf" required />
          </label>
          {uploadError && <p className="error">{uploadError}</p>}
          <button type="submit" disabled={uploading}>
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </form>

        {documents === null ? (
          <p className="muted">Loading documents...</p>
        ) : documents.length === 0 ? (
          <p className="muted">No documents uploaded yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Filename</th>
                <th>Status</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.filename}</td>
                  <td>
                    <span className={`status-badge status-${doc.status}`}>{doc.status}</span>
                  </td>
                  <td className="muted">{(doc.size_bytes / 1024).toFixed(1)} KB</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Search</h2>
        <form onSubmit={handleSearch}>
          <label>
            Query
            <input value={query} onChange={(e) => setQuery(e.target.value)} required />
          </label>
          {searchError && <p className="error">{searchError}</p>}
          <button type="submit" disabled={searching}>
            {searching ? "Searching..." : "Search"}
          </button>
        </form>

        {searchResults && (
          <>
            <p className="muted">
              {searchResults.results.length} result(s) · {searchResults.strategy} ·{" "}
              {searchResults.latency_ms.toFixed(0)}ms
            </p>
            {searchResults.results.map((result) => (
              <div key={result.chunk_id} className="search-result">
                <div className="search-result-meta">
                  <span>Page {result.page_number}</span>
                  <span>score {result.score.toFixed(3)}</span>
                </div>
                <p>{result.text}</p>
              </div>
            ))}
          </>
        )}
      </section>
    </main>
  );
}
