"use client";

import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { TraceEvalShowcase } from "@/components/TraceEvalShowcase";
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

interface DocumentPage {
  id: string;
  document_id: string;
  page_number: number;
  text: string;
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

interface ExtractedField {
  field_name: string;
  value: string;
  source_chunk_id: string;
  source_document_id: string;
  source_page_number: number;
}

interface ExtractionResponse {
  submission_id: string;
  status: string;
  fields: ExtractedField[];
}

interface AgentToolCall {
  sequence_index: number;
  tool_name: string;
  input_summary: string;
  output_summary: string;
}

interface AgentRun {
  id: string;
  submission_id: string;
  status: "completed" | "failed";
  recommendation: "approve" | "refer" | null;
  summary: string | null;
  error_message: string | null;
  requires_human_approval: boolean;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  tool_calls: AgentToolCall[];
}

const FIELD_LABELS: Record<string, string> = {
  named_insured: "Named insured",
  business_description: "Business description",
  requested_effective_date: "Requested effective date",
  requested_coverage_limit: "Requested coverage limit",
  broker_or_agent_name: "Broker or agent of record",
};

// The fixed set this system actually extracts (app/schemas/extraction.py)
// — shown even when a field wasn't found, so an absent value reads as a
// deliberate "not found in evidence" rather than silently missing from
// the table.
const ALL_FIELD_NAMES = Object.keys(FIELD_LABELS);

function parseToolCallFlags(outputSummary: string): string[] | null {
  try {
    const parsed: unknown = JSON.parse(outputSummary);
    if (
      parsed &&
      typeof parsed === "object" &&
      "flags" in parsed &&
      Array.isArray((parsed as { flags: unknown }).flags)
    ) {
      return (parsed as { flags: string[] }).flags;
    }
  } catch {
    // Not JSON, or not shaped as expected — fall back to showing it raw.
  }
  return null;
}

export default function SubmissionDetailPage() {
  const params = useParams<{ id: string }>();
  const submissionId = params.id;
  const router = useRouter();
  const { user, loading, csrfToken, memberships, activeOrganisationId } = useAuth();

  const activeRole = memberships.find((m) => m.organisation_id === activeOrganisationId)?.role;
  const canApprove = activeRole === "admin";

  const [submission, setSubmission] = useState<Submission | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState<string | null>(null);
  const [openEvidenceFor, setOpenEvidenceFor] = useState<string | null>(null);
  const [evidencePages, setEvidencePages] = useState<Record<string, DocumentPage[]>>({});
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [triaging, setTriaging] = useState(false);
  const [triageError, setTriageError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  const loadSubmission = useCallback(async () => {
    const data = await api.get<Submission>(`/submissions/${submissionId}`);
    setSubmission(data);
  }, [submissionId]);

  const loadDocuments = useCallback(async () => {
    const data = await api.get<DocumentItem[]>(`/submissions/${submissionId}/documents`);
    setDocuments(data);
  }, [submissionId]);

  const loadExtraction = useCallback(async () => {
    const data = await api.get<ExtractionResponse>(`/submissions/${submissionId}/extraction`);
    if (data.status !== "not_run") setExtraction(data);
  }, [submissionId]);

  const loadLatestAgentRun = useCallback(async () => {
    const runs = await api.get<AgentRun[]>(`/submissions/${submissionId}/agent-runs`);
    if (runs.length > 0) setAgentRun(runs[0]);
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
      void loadExtraction();
      void loadLatestAgentRun();
    }
  }, [user, loadSubmission, loadDocuments, loadExtraction, loadLatestAgentRun]);

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

  async function handleExtract() {
    if (!csrfToken) return;
    setExtractionError(null);
    setExtracting(true);
    try {
      const data = await api.post<ExtractionResponse>(
        `/submissions/${submissionId}/extract`,
        undefined,
        csrfToken,
      );
      setExtraction(data);
    } catch (err) {
      setExtractionError(err instanceof ApiError ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleRunTriage() {
    if (!csrfToken) return;
    setTriageError(null);
    setTriaging(true);
    try {
      const data = await api.post<AgentRun>(
        `/submissions/${submissionId}/agent-runs`,
        undefined,
        csrfToken,
      );
      setAgentRun(data);
    } catch (err) {
      setTriageError(err instanceof ApiError ? err.message : "Triage run failed");
    } finally {
      setTriaging(false);
    }
  }

  async function handleApprove() {
    if (!csrfToken || !agentRun) return;
    setApproveError(null);
    setApproving(true);
    try {
      const data = await api.post<AgentRun>(
        `/agent-runs/${agentRun.id}/approve`,
        undefined,
        csrfToken,
      );
      setAgentRun(data);
    } catch (err) {
      setApproveError(err instanceof ApiError ? err.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  }

  async function toggleEvidence(field: ExtractedField) {
    const key = `${field.field_name}:${field.source_document_id}:${field.source_page_number}`;
    if (openEvidenceFor === key) {
      setOpenEvidenceFor(null);
      return;
    }
    setOpenEvidenceFor(key);
    if (!evidencePages[field.source_document_id]) {
      setEvidenceError(null);
      try {
        const pages = await api.get<DocumentPage[]>(
          `/documents/${field.source_document_id}/pages`,
        );
        setEvidencePages((prev) => ({ ...prev, [field.source_document_id]: pages }));
      } catch (err) {
        setEvidenceError(err instanceof ApiError ? err.message : "Could not load source evidence");
      }
    }
  }

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading...</p>
      </main>
    );
  }

  const fieldsByName = new Map(extraction?.fields.map((f) => [f.field_name, f]) ?? []);

  return (
    <main className="wide">
      <div className="page-header">
        <h1>{submission?.title ?? "Submission"}</h1>
        {submission && <span className="status-badge">{submission.status}</span>}
      </div>

      <section className="card">
        <h2>1. Documents</h2>
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
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Size</th>
                  <th></th>
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
                    <td>
                      <a href={`/api/documents/${doc.id}/content`} target="_blank" rel="noreferrer">
                        Open PDF
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>2. Search evidence</h2>
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

      <section className="card">
        <h2>3. Extraction</h2>
        <p className="muted">
          Runs a real model call per document chunk, constrained to a fixed schema — a field with
          no supporting evidence is left null rather than guessed.
        </p>
        {extractionError && <p className="error">{extractionError}</p>}
        <button onClick={() => void handleExtract()} disabled={extracting}>
          {extracting ? "Extracting..." : "Run extraction"}
        </button>

        {extraction && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ALL_FIELD_NAMES.map((fieldName) => {
                  const field = fieldsByName.get(fieldName);
                  const key = field
                    ? `${field.field_name}:${field.source_document_id}:${field.source_page_number}`
                    : null;
                  const doc = field
                    ? documents?.find((d) => d.id === field.source_document_id)
                    : null;
                  return (
                    <Fragment key={fieldName}>
                      <tr>
                        <td>{FIELD_LABELS[fieldName]}</td>
                        <td>
                          {field ? (
                            field.value
                          ) : (
                            <span className="muted">not found in evidence</span>
                          )}
                        </td>
                        <td>
                          {field && (
                            <button
                              className="secondary"
                              onClick={() => void toggleEvidence(field)}
                            >
                              {openEvidenceFor === key ? "Hide evidence" : "View evidence"}
                            </button>
                          )}
                        </td>
                      </tr>
                      {field &&
                        openEvidenceFor === key &&
                        (() => {
                          const pagesForDoc = evidencePages[field.source_document_id];
                          const pageText = pagesForDoc?.find(
                            (p) => p.page_number === field.source_page_number,
                          )?.text;
                          return (
                            <tr>
                              <td colSpan={3}>
                                <div className="evidence-panel">
                                  {evidenceError ? (
                                    <p className="error">{evidenceError}</p>
                                  ) : !pagesForDoc ? (
                                    <p className="muted">Loading source page...</p>
                                  ) : (
                                    <>
                                      <p className="muted">
                                        {doc?.filename ?? "Document"}, page{" "}
                                        {field.source_page_number}
                                      </p>
                                      <p>{pageText ?? "Page text not found."}</p>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })()}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>4. Triage &amp; approval</h2>
        <p className="muted">
          The recommendation is always computed by deterministic rules — the model only narrates
          findings that are already decided.
        </p>
        {triageError && <p className="error">{triageError}</p>}
        <button onClick={() => void handleRunTriage()} disabled={triaging}>
          {triaging ? "Running triage..." : "Run triage"}
        </button>

        {agentRun && (
          <div className="triage-result">
            <div className="page-header">
              <span className={`status-badge status-${agentRun.status}`}>{agentRun.status}</span>
              {agentRun.recommendation && (
                <span className={`flag-badge flag-${agentRun.recommendation}`}>
                  {agentRun.recommendation === "approve" ? "Recommend: approve" : "Recommend: refer"}
                </span>
              )}
            </div>

            {agentRun.error_message && <p className="error">{agentRun.error_message}</p>}
            {agentRun.summary && <p>{agentRun.summary}</p>}

            {agentRun.tool_calls
              .filter((call) => call.tool_name === "apply_underwriting_rules")
              .map((call) => {
                const flags = parseToolCallFlags(call.output_summary);
                return flags && flags.length > 0 ? (
                  <ul key={call.sequence_index} className="flag-list">
                    {flags.map((flag, i) => (
                      <li key={i}>{flag}</li>
                    ))}
                  </ul>
                ) : null;
              })}

            <div className="approval-state">
              {agentRun.approved_at ? (
                <p className="muted">
                  Approved {new Date(agentRun.approved_at).toLocaleString()}
                </p>
              ) : agentRun.requires_human_approval ? (
                <>
                  <p className="muted">Awaiting human approval.</p>
                  {approveError && <p className="error">{approveError}</p>}
                  {canApprove ? (
                    <button onClick={() => void handleApprove()} disabled={approving}>
                      {approving ? "Approving..." : "Approve"}
                    </button>
                  ) : (
                    <p className="muted">Only an admin can approve this run.</p>
                  )}
                </>
              ) : null}
            </div>
          </div>
        )}
      </section>

      <TraceEvalShowcase />
    </main>
  );
}
