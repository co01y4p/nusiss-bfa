"use client";

import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";

type DocumentSummary = {
  id: string;
  title: string;
  source_path: string;
  version: string;
  access_scope: string;
  is_approved: boolean;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  heading: string;
  content: string;
  version: string;
  score: number;
};

type SearchResult = {
  query: string;
  results_count: number;
  chunks: RetrievedChunk[];
};

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Ingestion form state
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newScope, setNewScope] = useState("PUBLIC");
  const [newApproved, setNewApproved] = useState(true);
  const [ingesting, setIngesting] = useState(false);

  // Search sandbox state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMustApprove, setSearchMustApprove] = useState(true);
  const [searchTopK, setSearchTopK] = useState(5);
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  async function loadDocuments() {
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest<DocumentSummary[]>("/knowledge/documents");
      setDocuments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiRequest<DocumentSummary[]>("/knowledge/documents")
      .then((data) => {
        if (active) setDocuments(data);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Failed to load documents",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function toggleApproval(doc: DocumentSummary) {
    setError("");
    setSuccess("");
    try {
      const updated = await apiRequest<DocumentSummary>(
        `/knowledge/documents/${doc.id}/approval`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_approved: !doc.is_approved }),
        },
      );
      setDocuments((prev) => prev.map((d) => (d.id === doc.id ? updated : d)));
      setSuccess(
        `Document "${doc.title}" is now ${
          updated.is_approved
            ? "APPROVED (retrievable)"
            : "REVOKED (unapproved)"
        }.`,
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update approval",
      );
    }
  }

  async function deleteDoc(doc: DocumentSummary) {
    if (!confirm(`Delete document "${doc.title}" and all its chunks?`)) return;
    setError("");
    setSuccess("");
    try {
      await apiRequest(`/knowledge/documents/${doc.id}`, { method: "DELETE" });
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
      setSuccess(`Deleted document "${doc.title}".`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete document",
      );
    }
  }

  async function handleIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;
    setIngesting(true);
    setError("");
    setSuccess("");
    try {
      const created = await apiRequest<DocumentSummary>(
        "/knowledge/documents",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: newTitle.trim(),
            content: newContent.trim(),
            access_scope: newScope,
            is_approved: newApproved,
          }),
        },
      );
      setDocuments((prev) => [
        created,
        ...prev.filter((d) => d.id !== created.id),
      ]);
      setSuccess(
        `Ingested "${created.title}" into ${created.chunk_count} chunks!`,
      );
      setNewTitle("");
      setNewContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setIngesting(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await apiRequest<SearchResult>("/knowledge/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: searchQuery.trim(),
          access_scope: "PUBLIC",
          must_be_approved: searchMustApprove,
          top_k: Number(searchTopK),
        }),
      });
      setSearchResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function loadTemplate(title: string, text: string) {
    setNewTitle(title);
    setNewContent(text);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <section className="card">
        <h1>RAG Knowledge Base & RAG Testing Studio</h1>
        <p className="lede">
          Grounded retrieval engine powered by pgvector embeddings,
          heading-aware chunking, and strict citation validation.
        </p>

        {error && <div className="notice error">{error}</div>}
        {success && (
          <div
            className="notice"
            style={{
              background: "#e8f5e9",
              borderColor: "#a5d6a7",
              color: "#1b5e20",
            }}
          >
            {success}
          </div>
        )}
      </section>

      {/* 1. Knowledge Base Documents List */}
      <section className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <h2>Ingested Documents ({documents.length})</h2>
          <button
            type="button"
            onClick={loadDocuments}
            disabled={loading}
            style={{ width: "auto", padding: "0.4rem 0.8rem" }}
          >
            {loading ? "Refreshing..." : "Refresh List"}
          </button>
        </div>

        {documents.length === 0 ? (
          <p className="lede">
            No documents in the knowledge base yet. Ingest one below!
          </p>
        ) : (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
          >
            {documents.map((doc) => (
              <div
                key={doc.id}
                style={{
                  border: "1px solid #e0e0e0",
                  borderRadius: "8px",
                  padding: "1rem",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  background: doc.is_approved ? "#fafafa" : "#fff8e1",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <strong style={{ fontSize: "1.05rem" }}>{doc.title}</strong>
                    <span
                      className="pill"
                      style={{
                        background: doc.is_approved ? "#2e7d32" : "#e65100",
                        color: "#ffffff",
                        fontSize: "0.75rem",
                      }}
                    >
                      {doc.is_approved ? "APPROVED" : "UNAPPROVED"}
                    </span>
                    <span className="pill" style={{ fontSize: "0.75rem" }}>
                      Scope: {doc.access_scope}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "#666" }}>
                    <span>
                      Chunks: <strong>{doc.chunk_count}</strong>
                    </span>{" "}
                    | <span>Version: {doc.version}</span> |{" "}
                    <span>Source: {doc.source_path}</span>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    onClick={() => toggleApproval(doc)}
                    style={{
                      width: "auto",
                      padding: "0.4rem 0.8rem",
                      background: doc.is_approved ? "#ef6c00" : "#2e7d32",
                      color: "#fff",
                      fontSize: "0.85rem",
                    }}
                  >
                    {doc.is_approved ? "Revoke (Unapprove)" : "Approve"}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteDoc(doc)}
                    style={{
                      width: "auto",
                      padding: "0.4rem 0.8rem",
                      background: "#d32f2f",
                      color: "#fff",
                      fontSize: "0.85rem",
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 2. Interactive Search & Similarity Sandbox */}
      <section className="card">
        <h2>Vector & Hybrid Search Sandbox</h2>
        <p className="lede">
          Test raw pgvector cosine similarity + hybrid keyword matching before
          querying the full agent workflow.
        </p>

        <form
          onSubmit={handleSearch}
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
        >
          <div>
            <label htmlFor="search-query">Query Text</label>
            <input
              id="search-query"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. What are the air conditioning temperatures?"
              required
            />
          </div>

          <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={searchMustApprove}
                onChange={(e) => setSearchMustApprove(e.target.checked)}
              />
              Must be approved (RAG Rule)
            </label>

            <div
              style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
            >
              <label htmlFor="top-k">Top-K Chunks:</label>
              <input
                id="top-k"
                type="number"
                min="1"
                max="10"
                value={searchTopK}
                onChange={(e) => setSearchTopK(Number(e.target.value))}
                style={{ width: "60px" }}
              />
            </div>

            <button
              type="submit"
              disabled={searching}
              style={{ width: "auto", padding: "0.5rem 1.2rem" }}
            >
              {searching ? "Searching..." : "Test Vector Search"}
            </button>
          </div>
        </form>

        {searchResult && (
          <div style={{ marginTop: "1.25rem" }}>
            <h3>Search Results ({searchResult.results_count} chunks found)</h3>
            {searchResult.chunks.length === 0 ? (
              <div className="notice" style={{ marginTop: "0.5rem" }}>
                No chunks matched the query (or matched chunks belong to
                unapproved documents).
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                  marginTop: "0.5rem",
                }}
              >
                {searchResult.chunks.map((chunk, idx) => (
                  <div
                    key={chunk.chunk_id}
                    style={{
                      border: "1px solid #ddd",
                      borderRadius: "6px",
                      padding: "0.75rem 1rem",
                      background: "#fafafa",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "0.4rem",
                      }}
                    >
                      <strong>
                        #{idx + 1} {chunk.document_title} &gt; {chunk.heading}
                      </strong>
                      <span
                        className="pill"
                        style={{
                          background: "#1565c0",
                          color: "#fff",
                          fontSize: "0.75rem",
                        }}
                      >
                        Score: {chunk.score.toFixed(3)}
                      </span>
                    </div>
                    <p
                      style={{
                        margin: "0.25rem 0",
                        fontSize: "0.9rem",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {chunk.content}
                    </p>
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "#888",
                        marginTop: "0.3rem",
                      }}
                    >
                      Chunk ID: <code>{chunk.chunk_id}</code>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 3. Document Ingestion Studio */}
      <section className="card">
        <h2>Ingest New Document</h2>
        <p className="lede">
          Add Markdown or text documents into the knowledge base to test
          chunking and grounding immediately.
        </p>

        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            marginBottom: "1rem",
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: "0.85rem", alignSelf: "center" }}>
            Preset Templates:
          </span>
          <button
            type="button"
            className="small"
            style={{ width: "auto", padding: "0.3rem 0.6rem" }}
            onClick={() =>
              loadTemplate(
                "Parking and EV Charging Policy",
                "# Parking and EV Charging Policy\n\n## Visitor Parking\nVisitor parking is available in Basement 2 from 07:00 to 22:00 at $2.50 per hour.\n\n## Electric Vehicle Charging\nTen 22kW AC EV charging bays are located on B2 Lots 10-20. Charging is restricted to a 4-hour maximum duration.",
              )
            }
          >
            🚗 Parking & EV Policy
          </button>
          <button
            type="button"
            className="small"
            style={{ width: "auto", padding: "0.3rem 0.6rem" }}
            onClick={() =>
              loadTemplate(
                "Waste Disposal and Recycling Guidelines",
                "# Waste Disposal Guidelines\n\n## General Waste\nGeneral dry waste chutes are available on every floor lobby.\n\n## E-Waste Recycling\nE-waste collection bins for batteries and electronics are located at the Level 1 Loading Dock.",
              )
            }
          >
            ♻️ Waste Disposal
          </button>
        </div>

        <form
          onSubmit={handleIngest}
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
        >
          <div>
            <label htmlFor="doc-title">Document Title</label>
            <input
              id="doc-title"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Loading Bay and Delivery SOP"
              required
            />
          </div>

          <div>
            <label htmlFor="doc-content">
              Content (Markdown with Headings)
            </label>
            <textarea
              id="doc-content"
              rows={6}
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="# Heading 1&#10;&#10;## Section&#10;Rules and policies go here..."
              required
            />
          </div>

          <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
            <div>
              <label htmlFor="doc-scope">Access Scope:</label>
              <select
                id="doc-scope"
                value={newScope}
                onChange={(e) => setNewScope(e.target.value)}
                style={{ padding: "0.3rem 0.5rem" }}
              >
                <option value="PUBLIC">PUBLIC</option>
                <option value="STAFF">STAFF</option>
                <option value="MANAGEMENT">MANAGEMENT</option>
              </select>
            </div>

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={newApproved}
                onChange={(e) => setNewApproved(e.target.checked)}
              />
              Mark Approved Immediately
            </label>

            <button
              type="submit"
              disabled={ingesting}
              style={{ width: "auto", padding: "0.5rem 1.2rem" }}
            >
              {ingesting
                ? "Chunking & Ingesting..."
                : "Ingest & Chunk Document"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
