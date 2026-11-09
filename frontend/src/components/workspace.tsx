"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Copy,
  Download,
  Files,
  FileSearch,
  FileText,
  FolderOpen,
  Layers,
  LoaderCircle,
  Menu,
  MessageSquare,
  Moon,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useWorkspace, type WorkspaceState } from "@/lib/use-workspace";
import { type DocumentItem, type Source, sourceLocation } from "@/lib/models";
import { AnswerMessage } from "./answer";
import { Brand, FileBadge, Modal, StatusBadge } from "./ui";

const suggestions = [
  {
    icon: FileText,
    title: "Find the big picture",
    description: "Turn a long read into a clear summary.",
    prompt: "Summarize the key ideas and findings in the selected documents.",
  },
  {
    icon: Layers,
    title: "Connect the dots",
    description: "Compare ideas across your sources.",
    prompt:
      "Compare the main findings across the selected documents. Where do they agree or differ?",
  },
  {
    icon: FileSearch,
    title: "Go a little deeper",
    description: "Find the evidence behind the details.",
    prompt:
      "What are the most important results in the selected documents, and what qualifications or limitations should I keep in mind?",
  },
];

function Waiting({
  startedAt,
  cancel,
}: {
  startedAt: number;
  cancel: () => void;
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [startedAt]);
  return (
    <div className="waiting" role="status">
      <Brand small />
      <div>
        <strong>
          Making sense of your sources
          <span className="thinking-dots">
            <i />
            <i />
            <i />
          </span>
        </strong>
        <p>
          {seconds < 25
            ? "Your answer will appear after the evidence checks finish."
            : "Still working. Detailed questions and provider limits can take a little longer."}
        </p>
      </div>
      <span className="elapsed">{seconds}s</span>
      <button
        className="icon-button"
        aria-label="Stop waiting for answer"
        title="Stop waiting for this answer"
        onClick={cancel}
      >
        <Square size={14} />
      </button>
    </div>
  );
}

export function Workspace() {
  const workspace = useWorkspace();
  const [view, setView] = useState<"chat" | "documents">("chat");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const [sourceView, setSourceView] = useState<{
    sources: Source[];
    index: number;
  } | null>(null);
  const [theme, setTheme] = useState("light");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [draft, setDraft] = useState("");
  const [dragging, setDragging] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<string[] | null>(null);
  const [scopeQuery, setScopeQuery] = useState("");
  const composer = useRef<HTMLTextAreaElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const messagesArea = useRef<HTMLDivElement>(null);
  const [showScroll, setShowScroll] = useState(false);
  const messageCount = workspace.active?.messages.length ?? 0;
  const hasMessages = messageCount > 0;
  const scopeIds = workspace.active?.docIds ?? null;
  const isReady = workspace.health?.status === "ok";

  useEffect(() => {
    try {
      const saved = localStorage.getItem("folio.theme");
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved === "dark") setTheme("dark");
    } catch {
      /* Theme remains light when storage is unavailable. */
    }
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("folio.theme", theme);
    } catch {
      /* Theme still works for this visit. */
    }
  }, [theme]);
  useEffect(() => {
    if (view === "chat")
      bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messageCount, workspace.pending, workspace.active?.id, view]);
  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = "auto";
      composer.current.style.height = `${Math.min(composer.current.scrollHeight, 176)}px`;
    }
  }, [draft]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setView("documents");
        setTimeout(
          () =>
            document
              .querySelector<HTMLInputElement>(".library-search input")
              ?.focus(),
          50,
        );
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  function changeView(next: "chat" | "documents") {
    setView(next);
    setMobileOpen(false);
  }
  function startChat() {
    workspace.newConversation();
    setDraft("");
    changeView("chat");
    setTimeout(() => composer.current?.focus(), 50);
  }
  function showScope() {
    setScopeDraft(scopeIds);
    setScopeQuery("");
    setScopeOpen(true);
  }
  async function submit(text = draft) {
    if (!text.trim() || !workspace.canSend) return;
    setDraft("");
    await workspace.send(text);
    composer.current?.focus();
  }
  function suggest(prompt: string) {
    setDraft(prompt);
    setView("chat");
    setTimeout(() => composer.current?.focus(), 50);
  }
  function downloadConversation() {
    if (!workspace.active?.messages.length) return;
    const text =
      `# ${workspace.active.title}\n\n` +
      workspace.active.messages
        .map(
          (m) =>
            `## ${m.role === "user" ? "You" : "Folio"}\n\n${m.error || m.text}`,
        )
        .join("\n\n---\n\n");
    const url = URL.createObjectURL(
      new Blob([text], { type: "text/markdown;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "folio-conversation.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const busyJobs = workspace.jobs.filter(
    (j) => j.status === "queued" || j.status === "processing",
  );
  const sidebar = (
    <>
      <div className="sidebar-top">
        <Link className="brand-link" href="/" aria-label="Folio home">
          <Brand />
        </Link>
        <span className="workspace-tag">WORKSPACE</span>
      </div>
      <button
        className="new-chat"
        onClick={startChat}
        disabled={!!workspace.pending}
      >
        <Plus size={17} /> New conversation <span>↗</span>
      </button>
      <nav aria-label="Workspace">
        <button
          className={`nav-item ${view === "chat" ? "active" : ""}`}
          onClick={() => changeView("chat")}
        >
          <MessageSquare size={18} /> Ask your documents
        </button>
        <button
          className={`nav-item ${view === "documents" ? "active" : ""}`}
          onClick={() => changeView("documents")}
        >
          <FolderOpen size={18} /> Document library{" "}
          <span className="count">{workspace.documents.length}</span>
        </button>
      </nav>
      <div className="sidebar-section">
        <div className="sidebar-label">RECENT CONVERSATIONS</div>
        <div className="recent-list">
          {workspace.conversations
            .filter((c) => c.messages.length)
            .slice(0, 10)
            .map((c) => (
              <div
                className={`recent-row ${c.id === workspace.active?.id && view === "chat" ? "current" : ""}`}
                key={c.id}
              >
                <button
                  className="recent-title"
                  title={c.title}
                  disabled={!!workspace.pending}
                  onClick={() => {
                    workspace.chooseConversation(c.id);
                    setDraft("");
                    changeView("chat");
                  }}
                >
                  <MessageSquare size={14} />
                  <span>{c.title}</span>
                </button>
                <button
                  className="recent-remove icon-button"
                  aria-label={`Remove conversation: ${c.title}`}
                  title="Remove from this browser"
                  disabled={!!workspace.pending}
                  onClick={() => workspace.removeConversation(c.id)}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          {!workspace.conversations.some((c) => c.messages.length) && (
            <p className="sidebar-empty">
              Your next good question
              <br />
              starts a conversation.
            </p>
          )}
        </div>
      </div>
      <div className="sidebar-documents">
        <div className="sidebar-label">
          YOUR SOURCES{" "}
          <button
            className="icon-button"
            aria-label="Upload documents"
            onClick={() => setUploadOpen(true)}
          >
            <Plus size={15} />
          </button>
        </div>
        {workspace.documents.slice(0, 4).map((doc) => (
          <button
            className="sidebar-doc"
            key={doc.id}
            title={doc.name}
            onClick={() => changeView("documents")}
          >
            <FileBadge name={doc.name} small />
            <span>{doc.name}</span>
            <span
              className={`tiny-status ${doc.status}`}
              aria-label={doc.status}
            />
          </button>
        ))}
        {workspace.documents.length > 4 && (
          <button
            className="text-button sidebar-more"
            onClick={() => changeView("documents")}
          >
            View all {workspace.documents.length} documents{" "}
            <ArrowRight size={13} />
          </button>
        )}
        {!workspace.documents.length && (
          <div className="sidebar-source-empty">
            <Files size={24} />
            <span>A home for your knowledge.</span>
          </div>
        )}
      </div>
      <div className="sidebar-bottom">
        <button className="sidebar-upload" onClick={() => setUploadOpen(true)}>
          <Upload size={17} />
          <span>
            Add your documents<small>PDF, Word, text & Markdown</small>
          </span>
          <Plus size={15} />
        </button>
        {busyJobs.length > 0 && (
          <button
            className="indexing-indicator"
            onClick={() => changeView("documents")}
          >
            <LoaderCircle size={13} className="spin" /> {busyJobs.length}{" "}
            {busyJobs.length === 1 ? "document" : "documents"} processing
          </button>
        )}
        <div className="workspace-footer">
          <span className="workspace-avatar">F</span>
          <div>
            <strong>Personal workspace</strong>
            <small>Saved on this device</small>
          </div>
          <button
            className="icon-button"
            aria-label="Workspace settings"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 size={17} />
          </button>
        </div>
      </div>
    </>
  );

  const displayedDocuments = workspace.documents.filter(
    (doc) =>
      doc.name.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "indexed"
          ? doc.status === "indexed"
          : filter === "failed"
            ? doc.status === "failed"
            : !["indexed", "failed"].includes(doc.status))),
  );

  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <aside className="sidebar">{sidebar}</aside>
      <main id="main" className="workspace-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {view === "documents"
                ? "Document library"
                : hasMessages
                  ? "Conversation"
                  : "Overview"}
            </strong>
          </div>
          <div className="topbar-actions">
            <button
              className={`connection-pill ${isReady ? "connected" : "disconnected"}`}
              onClick={() => setSettingsOpen(true)}
            >
              <span />
              {isReady
                ? "Connected"
                : workspace.loaded
                  ? "Check connection"
                  : "Connecting"}
            </button>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
              title="Change theme"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={17} /> : <Sun size={18} />}
            </button>
            <button
              className="icon-button help-button"
              aria-label="About this workspace"
              onClick={() => setSettingsOpen(true)}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        {workspace.storageError && (
          <div className="workspace-banner" role="alert">
            Browser storage is full or unavailable. This conversation may not be
            saved after you close the page.
          </div>
        )}
        {workspace.documentError && (
          <div className="workspace-banner" role="alert">
            <span>{workspace.documentError}</span>
            <button
              onClick={() => {
                void workspace.refreshDocuments();
                void workspace.refreshHealth();
              }}
            >
              Reconnect <RefreshCw size={13} />
            </button>
          </div>
        )}
        {view === "chat" ? (
          <div
            className={`chat-view ${hasMessages ? "has-messages" : "empty-chat"}`}
          >
            {hasMessages && (
              <div className="conversation-heading">
                <div>
                  <span className="eyebrow">CONVERSATION</span>
                  <h1>{workspace.active?.title}</h1>
                </div>
                <button
                  className="icon-button"
                  aria-label="Download conversation"
                  title="Download as Markdown"
                  onClick={downloadConversation}
                >
                  <Download size={18} />
                </button>
              </div>
            )}
            <div
              className="conversation-scroll"
              ref={messagesArea}
              onScroll={() => {
                const el = messagesArea.current;
                if (el)
                  setShowScroll(
                    el.scrollHeight - el.scrollTop - el.clientHeight > 240,
                  );
              }}
            >
              {!hasMessages ? (
                <div className="welcome">
                  <div className="welcome-intro">
                    <div className="welcome-copy">
                      <div className="eyebrow welcome-eyebrow">
                        <span /> A LITTLE MORE CLARITY
                      </div>
                      <h1>
                        Your documents.
                        <br />
                        <em>A world of answers.</em>
                      </h1>
                      <p>
                        Bring your sources together. Find what matters.
                        <br className="desktop-break" /> Every insight, a little
                        closer to the evidence.
                      </p>
                      <div className="welcome-detail">
                        <span className="mini-source">
                          <BookOpen size={13} />
                        </span>
                        {workspace.indexed.length ? (
                          <span>
                            <b>{workspace.indexed.length}</b>{" "}
                            {workspace.indexed.length === 1
                              ? "source ready"
                              : "sources ready"}{" "}
                            to explore
                          </span>
                        ) : (
                          <span>
                            Your next discovery starts with a document
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="paper-illustration" aria-hidden="true">
                      <div className="paper paper-back">
                        <div />
                        <div />
                        <div />
                      </div>
                      <div className="paper paper-front">
                        <div className="paper-heading">
                          <span />
                          <i />
                        </div>
                        <div className="paper-line long" />
                        <div className="paper-line" />
                        <div className="paper-highlight" />
                        <div className="paper-line short" />
                        <div className="paper-chart">
                          <i />
                          <i />
                          <i />
                          <i />
                          <i />
                        </div>
                        <span className="paper-foot">A clearer picture.</span>
                      </div>
                      <div className="citation-stamp">
                        <CheckCheck size={16} />
                        <span>Backed by your sources</span>
                      </div>
                      <Sparkles
                        className="paper-spark"
                        size={21}
                        strokeWidth={1.3}
                      />
                    </div>
                  </div>
                  {!workspace.loaded ? (
                    <div className="library-loading" role="status">
                      <LoaderCircle size={18} className="spin" /> Bringing your
                      workspace together…
                    </div>
                  ) : !workspace.documents.length &&
                    !workspace.documentError ? (
                    <button
                      className="welcome-upload"
                      onClick={() => setUploadOpen(true)}
                    >
                      <span className="upload-orbit">
                        <Upload size={21} />
                      </span>
                      <span>
                        <strong>Make room for your next idea.</strong>
                        <small>Add a document to start asking questions.</small>
                      </span>
                      <span className="button primary">
                        Add documents <Plus size={15} />
                      </span>
                    </button>
                  ) : null}
                  <div className="suggestion-heading">
                    <span>A FEW PLACES TO START</span>
                    <span>
                      Follow your curiosity <ArrowDown size={12} />
                    </span>
                  </div>
                  <div className="suggestions">
                    {suggestions.map(
                      ({ icon: Icon, title, description, prompt }, index) => (
                        <button
                          className={`suggestion suggestion-${index}`}
                          key={title}
                          onClick={() => suggest(prompt)}
                        >
                          <span className="suggestion-icon">
                            <Icon size={20} strokeWidth={1.6} />
                          </span>
                          <strong>{title}</strong>
                          <p>{description}</p>
                          <ArrowUpRight
                            className="suggestion-arrow"
                            size={17}
                          />
                        </button>
                      ),
                    )}
                  </div>
                  <div className="welcome-note">
                    <ShieldCheck size={14} />
                    <span>
                      Built to show its sources. Designed to admit what it
                      doesn’t know.
                    </span>
                  </div>
                </div>
              ) : (
                <div className="messages">
                  {workspace.active?.messages.map((message, messageIndex) =>
                    message.role === "user" ? (
                      <article className="user-message" key={message.id}>
                        <div className="user-label">YOU</div>
                        <p>{message.text}</p>
                      </article>
                    ) : (
                      <AnswerMessage
                        key={message.id}
                        message={message}
                        onSource={(sources, index) =>
                          setSourceView({ sources, index })
                        }
                        onRetry={() =>
                          void submit(
                            workspace.active?.messages
                              .slice(0, messageIndex)
                              .findLast((m) => m.role === "user")?.text || "",
                          )
                        }
                        disabled={!workspace.canSend}
                      />
                    ),
                  )}
                  {workspace.pending && (
                    <Waiting
                      startedAt={workspace.pending.startedAt}
                      cancel={workspace.cancel}
                    />
                  )}
                  <div ref={bottom} />
                </div>
              )}
            </div>
            <div className="composer-area">
              {showScroll && hasMessages && (
                <button
                  className="scroll-bottom"
                  aria-label="Scroll to latest answer"
                  onClick={() =>
                    bottom.current?.scrollIntoView({ behavior: "smooth" })
                  }
                >
                  <ArrowDown size={17} />
                </button>
              )}
              {workspace.invalidSelection && (
                <div className="scope-warning" role="status">
                  {scopeIds?.length
                    ? "Some selected documents aren’t ready or are no longer available."
                    : "Select at least one document to ask a question."}
                  <button className="text-button" onClick={showScope}>
                    Choose sources
                  </button>
                </div>
              )}
              <form
                className={`composer ${workspace.pending ? "composer-busy" : ""}`}
                onSubmit={(event) => {
                  event.preventDefault();
                  void submit();
                }}
              >
                <div className="composer-context">
                  <button
                    type="button"
                    className="scope-picker"
                    disabled={!!workspace.pending}
                    onClick={showScope}
                  >
                    <Layers size={14} />
                    {scopeIds === null
                      ? "All documents"
                      : `${scopeIds.length} selected ${scopeIds.length === 1 ? "document" : "documents"}`}
                    <ChevronDown size={13} />
                  </button>
                  <span className="composer-context-count">
                    {workspace.available.length} ready
                  </span>
                </div>
                <label className="sr-only" htmlFor="question">
                  Ask a question about your documents
                </label>
                <textarea
                  id="question"
                  ref={composer}
                  value={draft}
                  rows={2}
                  maxLength={8000}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={
                    workspace.indexed.length
                      ? "Ask a question. Find a connection. Explore an idea…"
                      : "Add your documents, then ask anything about them…"
                  }
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      void submit();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <button
                    type="button"
                    className="composer-attach"
                    onClick={() => setUploadOpen(true)}
                    aria-label="Attach documents"
                  >
                    <Paperclip size={17} />
                    <span>Add sources</span>
                  </button>
                  <span className="composer-shortcut">
                    {draft.length > 7500
                      ? `${draft.length}/8000`
                      : "Enter to send · Shift + Enter for a new line"}
                  </span>
                  {workspace.pending ? (
                    <button
                      type="button"
                      className="send-button"
                      aria-label="Stop waiting"
                      onClick={workspace.cancel}
                    >
                      <Square size={15} />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      className="send-button"
                      aria-label="Send message"
                      disabled={!draft.trim() || !workspace.canSend}
                    >
                      <ArrowUp size={19} />
                    </button>
                  )}
                </div>
              </form>
              <div className="composer-footnote">
                Answers stay grounded in your sources. Always review important
                details.
              </div>
            </div>
          </div>
        ) : (
          <section className="library-view">
            <div className="library-title">
              <div>
                <div className="eyebrow">YOUR KNOWLEDGE, IN ONE PLACE</div>
                <h1>
                  The document library<span>.</span>
                </h1>
                <p>
                  Good answers start with good sources. Build your collection
                  here.
                </p>
              </div>
              <button
                className="button primary"
                onClick={() => setUploadOpen(true)}
              >
                <Plus size={16} /> Add documents
              </button>
            </div>
            <div className="library-toolbar">
              <div
                className="library-tabs"
                role="group"
                aria-label="Filter documents"
              >
                {[
                  ["all", "All sources"],
                  ["indexed", "Ready"],
                  ["processing", "Processing"],
                  ["failed", "Needs attention"],
                ].map(([value, title]) => (
                  <button
                    key={value}
                    aria-pressed={filter === value}
                    className={filter === value ? "selected" : ""}
                    onClick={() => setFilter(value)}
                  >
                    {title}
                    {value === "all" && (
                      <span>{workspace.documents.length}</span>
                    )}
                  </button>
                ))}
              </div>
              <label className="library-search">
                <Search size={16} />
                <input
                  aria-label="Search documents"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a document…"
                />
                <kbd>⌘ K</kbd>
              </label>
              <button
                className="icon-button refresh-docs"
                title="Refresh documents"
                aria-label="Refresh documents"
                onClick={() => void workspace.refreshDocuments()}
              >
                <RefreshCw size={17} />
              </button>
            </div>
            {workspace.jobPollError && (
              <p className="inline-warning" role="status">
                Processing updates are temporarily unavailable. Retrying
                automatically.
              </p>
            )}
            {!workspace.loaded ? (
              <div className="empty-library">
                <LoaderCircle className="spin" />
                <h2>Loading your library…</h2>
              </div>
            ) : displayedDocuments.length ? (
              <div className="document-table">
                <div className="document-table-heading">
                  <span>DOCUMENT</span>
                  <span>STATUS</span>
                  <span>ACTIONS</span>
                </div>
                {displayedDocuments.map((doc) => {
                  const job = workspace.jobs.find(
                    (j) => j.document_id === doc.id,
                  );
                  const busy = workspace.busyDocument === doc.id;
                  const processing = !["indexed", "failed"].includes(
                    doc.status,
                  );
                  return (
                    <div className="document-row" key={doc.id}>
                      <div className="document-title-cell">
                        <FileBadge name={doc.name} />
                        <div>
                          <strong title={doc.name}>{doc.name}</strong>
                          <small>
                            {doc.status === "indexed"
                              ? "Ready to ask, compare, and explore"
                              : doc.status === "failed"
                                ? "Reindex to try processing this document again"
                                : "Preparing this source for your questions"}
                          </small>
                          {job?.error && (
                            <p className="document-job-error">{job.error}</p>
                          )}
                          {job && (
                            <details className="job-meta">
                              <summary>Processing details</summary>
                              <span>Job: {job.job_id}</span>
                              <span>Status: {job.status}</span>
                            </details>
                          )}
                        </div>
                      </div>
                      <StatusBadge status={doc.status} />
                      <div className="document-actions">
                        <button
                          className="icon-button"
                          aria-label={`Ask about ${doc.name}`}
                          title="Ask about this document"
                          disabled={
                            doc.status !== "indexed" || !!workspace.pending
                          }
                          onClick={() => {
                            workspace.setScope([doc.id]);
                            changeView("chat");
                            setTimeout(() => composer.current?.focus(), 50);
                          }}
                        >
                          <MessageSquare size={16} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label={`Reindex ${doc.name}`}
                          title="Reindex document"
                          disabled={busy || processing}
                          onClick={() => void workspace.reindex(doc)}
                        >
                          <RefreshCw size={16} className={busy ? "spin" : ""} />
                        </button>
                        <button
                          className="icon-button danger-hover"
                          aria-label={`Delete ${doc.name}`}
                          title="Delete document"
                          disabled={busy || processing || !!workspace.pending}
                          onClick={() => setDeleteTarget(doc)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-library">
                <div className="empty-library-icon">
                  <FolderOpen size={33} strokeWidth={1.3} />
                </div>
                <h2>
                  {workspace.documents.length
                    ? "No matching sources"
                    : "Your knowledge belongs here."}
                </h2>
                <p>
                  {workspace.documents.length
                    ? "Try another search or change the filter."
                    : "Add your first document. We’ll turn it into something you can explore."}
                </p>
                <button
                  className="button secondary"
                  onClick={() =>
                    workspace.documents.length
                      ? (setQuery(""), setFilter("all"))
                      : setUploadOpen(true)
                  }
                >
                  {workspace.documents.length
                    ? "Clear filters"
                    : "Add your first source"}
                  <ArrowRight size={15} />
                </button>
              </div>
            )}
            <div className="library-footer">
              <ShieldCheck size={15} /> Your files are stored in your backend.
              Retrieved excerpts are sent to your configured AI provider when
              you ask a question.
            </div>
          </section>
        )}
      </main>
      <Modal
        open={mobileOpen}
        onOpenChange={setMobileOpen}
        title="Your workspace"
      >
        <div className="mobile-sidebar">{sidebar}</div>
      </Modal>
      <Modal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        title="A home for your knowledge."
        description="Add a few sources. Let your next question lead the way."
        wide
      >
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          className="sr-only"
          aria-label="Choose files to upload"
          onChange={(event) => {
            void workspace.upload(Array.from(event.target.files || []));
            event.target.value = "";
          }}
        />
        <button
          className={`dropzone ${dragging ? "dragging" : ""}`}
          disabled={!!workspace.uploading}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void workspace.upload(Array.from(e.dataTransfer.files));
          }}
        >
          <div className="upload-art">
            <FileText size={26} />
            <Upload size={21} />
          </div>
          <strong>
            {workspace.uploading
              ? `Uploading ${workspace.uploading}`
              : dragging
                ? "Drop your next discovery here"
                : "Drop your documents here"}
          </strong>
          <span>
            {workspace.uploading ? (
              "Keep this tab open while the file uploads."
            ) : (
              <>
                or <b>browse files</b> on your device
              </>
            )}
          </span>
          <small>PDF, DOCX, TXT, MD · Up to 50 MB per file</small>
        </button>
        {workspace.fileErrors.map((error, i) => (
          <div key={i} className="upload-error" role="alert">
            <strong>{error.name}</strong>
            <p>{error.message}</p>
          </div>
        ))}
        {!!workspace.jobs.length && (
          <div className="upload-jobs">
            <div className="eyebrow">RECENT IMPORTS</div>
            {workspace.jobs
              .slice(-4)
              .reverse()
              .map((job) => (
                <div className="upload-job" key={job.job_id}>
                  {job.status === "completed" ? (
                    <Check size={17} />
                  ) : job.status === "failed" ? (
                    <X size={17} />
                  ) : (
                    <LoaderCircle size={17} className="spin" />
                  )}
                  <div>
                    <strong>
                      {workspace.documents.find((d) => d.id === job.document_id)
                        ?.name || "Document"}
                    </strong>
                    <small>
                      {job.error ||
                        {
                          completed: "Ready for your questions",
                          queued: "Waiting to be processed",
                          processing: "Reading and indexing your document",
                          failed: "Processing failed",
                        }[job.status]}
                    </small>
                  </div>
                  <span className={`job-dot ${job.status}`} />
                </div>
              ))}
          </div>
        )}
        <p className="modal-note">
          <ShieldCheck size={14} /> Files stay in your backend. Relevant
          excerpts are shared with your AI provider when answering.
        </p>
        <div className="modal-footer">
          <span>Scanned PDFs need searchable text before upload.</span>
          <button
            className="button secondary"
            onClick={() => {
              setUploadOpen(false);
              setView("documents");
            }}
          >
            View library <ArrowRight size={14} />
          </button>
        </div>
      </Modal>
      <Modal
        open={scopeOpen}
        onOpenChange={setScopeOpen}
        title="Choose your sources"
        description="Focus this conversation on the documents that matter."
      >
        <label className="scope-all">
          <input
            type="checkbox"
            checked={scopeDraft === null}
            onChange={(e) => setScopeDraft(e.target.checked ? null : [])}
          />
          <span>
            <strong>All ready documents</strong>
            <small>Include new documents as they finish indexing.</small>
          </span>
          <Layers size={19} />
        </label>
        <label className="scope-search">
          <Search size={16} />
          <input
            value={scopeQuery}
            onChange={(e) => setScopeQuery(e.target.value)}
            placeholder="Search your sources…"
            aria-label="Search sources"
          />
        </label>
        <div className="scope-list">
          {workspace.documents
            .filter((d) =>
              d.name.toLowerCase().includes(scopeQuery.toLowerCase()),
            )
            .map((doc) => (
              <label
                className={`scope-option ${doc.status !== "indexed" ? "unavailable" : ""}`}
                key={doc.id}
              >
                <input
                  type="checkbox"
                  disabled={doc.status !== "indexed"}
                  checked={
                    scopeDraft === null
                      ? doc.status === "indexed"
                      : scopeDraft.includes(doc.id)
                  }
                  onChange={(e) => {
                    const previous =
                      scopeDraft ?? workspace.indexed.map((d) => d.id);
                    if (e.target.checked && previous.length >= 30) {
                      workspace.setNotice(
                        "You can select up to 30 documents at a time.",
                      );
                      return;
                    }
                    setScopeDraft(
                      e.target.checked
                        ? [...previous, doc.id]
                        : previous.filter((id) => id !== doc.id),
                    );
                  }}
                />
                <FileBadge name={doc.name} small />
                <span>{doc.name}</span>
                <StatusBadge status={doc.status} />
              </label>
            ))}
          {!workspace.documents.length && (
            <p className="empty-scope">
              Upload a document to choose your sources.
            </p>
          )}
          {scopeDraft?.some(
            (id) => !workspace.documents.some((d) => d.id === id),
          ) && (
            <button
              className="text-button"
              onClick={() =>
                setScopeDraft(
                  scopeDraft.filter((id) =>
                    workspace.documents.some((d) => d.id === id),
                  ),
                )
              }
            >
              Remove unavailable selections
            </button>
          )}
        </div>
        <div className="modal-footer">
          <span>
            {scopeDraft === null
              ? "All indexed documents"
              : `${scopeDraft.length} selected`}
          </span>
          <button
            className="button primary"
            onClick={() => {
              workspace.setScope(scopeDraft);
              setScopeOpen(false);
            }}
          >
            Apply selection <Check size={15} />
          </button>
        </div>
      </Modal>
      <Modal
        open={!!sourceView}
        onOpenChange={(open) => {
          if (!open) setSourceView(null);
        }}
        title="Follow the evidence"
        description="An exact excerpt returned with this answer."
        drawer
      >
        {sourceView && (
          <SourceInspector
            sourceView={sourceView}
            onChange={(index) => setSourceView({ ...sourceView, index })}
            workspace={workspace}
          />
        )}
      </Modal>
      <Modal
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open && !workspace.busyDocument) setDeleteTarget(null);
        }}
        title="Remove this document?"
        description="This removes the file and its indexed content from your library."
      >
        <div className="delete-document-preview">
          <FileBadge name={deleteTarget?.name || "Document"} />
          <strong>{deleteTarget?.name}</strong>
        </div>
        <p className="modal-note">
          Existing conversations may still show historical citations. You can
          upload the file again later.
        </p>
        <div className="modal-footer">
          <button
            className="button secondary"
            onClick={() => setDeleteTarget(null)}
            disabled={!!workspace.busyDocument}
          >
            Keep document
          </button>
          <button
            className="button danger"
            disabled={!!workspace.busyDocument}
            onClick={async () => {
              if (
                deleteTarget &&
                (await workspace.deleteDocument(deleteTarget))
              )
                setDeleteTarget(null);
            }}
          >
            {workspace.busyDocument ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Trash2 size={15} />
            )}{" "}
            Remove document
          </button>
        </div>
      </Modal>
      <Modal
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        title="Your workspace, thoughtfully simple."
        description="Everything you need to know about this space."
      >
        <div className="settings-section">
          <div className="settings-section-title">
            <span>CONNECTION</span>
            <button
              className="icon-button"
              aria-label="Check connection"
              onClick={() => {
                void workspace.refreshDocuments();
                void workspace.refreshHealth();
              }}
            >
              <RefreshCw size={15} />
            </button>
          </div>
          {["sqlite", "qdrant", "redis"].map((name) => (
            <div className="service-row" key={name}>
              <span>
                {
                  {
                    sqlite: "Document storage",
                    qdrant: "Search index",
                    redis: "Processing queue",
                  }[name]
                }
              </span>
              <span
                className={
                  workspace.health?.dependencies[name] === "ok"
                    ? "service-online"
                    : "service-offline"
                }
              >
                <i />
                {workspace.health?.dependencies[name] === "ok"
                  ? "Connected"
                  : "Unavailable"}
              </span>
            </div>
          ))}
          <p className="settings-caption">
            These checks verify storage and search services. AI provider
            availability is checked when you ask a question.
          </p>
        </div>
        <div className="settings-section">
          <div className="settings-section-title">
            <span>APPEARANCE</span>
          </div>
          <div className="theme-options">
            <button
              className={theme === "light" ? "chosen" : ""}
              onClick={() => setTheme("light")}
            >
              <Sun size={18} /> Light{theme === "light" && <Check size={15} />}
            </button>
            <button
              className={theme === "dark" ? "chosen" : ""}
              onClick={() => setTheme("dark")}
            >
              <Moon size={18} /> Dark{theme === "dark" && <Check size={15} />}
            </button>
          </div>
        </div>
        <div className="settings-section">
          <div className="settings-section-title">
            <span>YOUR DATA</span>
          </div>
          <p>
            Conversation history is saved in this browser. It won’t
            automatically appear on another device. Your backend also stores
            conversation turns.
          </p>
          <p>
            Uploaded files stay in your backend. Retrieved excerpts are sent to
            your configured AI provider to prepare and check answers.
          </p>
          <button
            className="text-button danger-text"
            disabled={!!workspace.pending}
            onClick={() => {
              setSettingsOpen(false);
              setClearOpen(true);
            }}
          >
            <Trash2 size={14} /> Clear browser conversation history
          </button>
        </div>
      </Modal>
      <Modal
        open={clearOpen}
        onOpenChange={setClearOpen}
        title="Clear this browser’s history?"
        description="Your uploaded documents and backend conversation records will stay in place."
      >
        <div className="modal-footer">
          <button
            className="button secondary"
            onClick={() => setClearOpen(false)}
          >
            Keep history
          </button>
          <button
            className="button danger"
            onClick={() => {
              workspace.clearHistory();
              setClearOpen(false);
              setView("chat");
            }}
          >
            Clear browser history
          </button>
        </div>
      </Modal>
      {workspace.notice && (
        <div className="toast" role="status">
          <span>{workspace.notice}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => workspace.setNotice(null)}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function SourceInspector({
  sourceView,
  onChange,
  workspace,
}: {
  sourceView: { sources: Source[]; index: number };
  onChange: (index: number) => void;
  workspace: WorkspaceState;
}) {
  const source = sourceView.sources[sourceView.index];
  const isAvailable = workspace.documents.some(
    (d) => d.id === source.document_id,
  );
  async function copy() {
    try {
      await navigator.clipboard.writeText(
        `${source.document_name} — ${sourceLocation(source)}\n\n${source.quote}`,
      );
      workspace.setNotice("Source excerpt copied.");
    } catch {
      workspace.setNotice("Select the excerpt text to copy it.");
    }
  }
  return (
    <div className="source-inspector">
      <div className="source-document-heading">
        <FileBadge name={source.document_name} />
        <div>
          <strong>{source.document_name}</strong>
          <span>{sourceLocation(source)}</span>
        </div>
      </div>
      <div className="source-navigation">
        <span>
          EXCERPT {sourceView.index + 1} OF {sourceView.sources.length}
        </span>
        <div>
          <button
            className="icon-button"
            aria-label="Previous source excerpt"
            disabled={sourceView.index === 0}
            onClick={() => onChange(sourceView.index - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Next source excerpt"
            disabled={sourceView.index === sourceView.sources.length - 1}
            onClick={() => onChange(sourceView.index + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
      </div>
      {!isAvailable && workspace.loaded && (
        <p className="inline-warning">
          This document is no longer in your current library. This is the
          excerpt saved with the answer.
        </p>
      )}
      <blockquote className="source-quote">{source.quote}</blockquote>
      <div className="source-caption">
        <ShieldCheck size={14} /> Source wording is preserved, including any
        extraction artifacts.
      </div>
      <button
        className="button secondary source-copy"
        onClick={() => void copy()}
      >
        <Copy size={15} /> Copy excerpt
      </button>
      <div className="source-related">
        <span className="eyebrow">IN THIS ANSWER</span>
        {sourceView.sources.map((item, index) => (
          <button
            className={index === sourceView.index ? "selected" : ""}
            key={item.chunk_id}
            onClick={() => onChange(index)}
          >
            <span>{index + 1}</span>
            <div>
              <strong>{item.document_name}</strong>
              <small>{sourceLocation(item)}</small>
            </div>
            <ArrowUpRight size={14} />
          </button>
        ))}
      </div>
    </div>
  );
}
