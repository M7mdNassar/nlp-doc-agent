"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorText } from "./api";
import {
  Conversation,
  DocumentItem,
  Health,
  Job,
  Message,
  STORAGE_KEY,
  makeConversation,
  savedSchema,
  validateFile,
} from "./models";

export function useWorkspace() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [storageError, setStorageError] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<
    { name: string; message: string }[]
  >([]);
  const [pending, setPending] = useState<{
    conversationId: string;
    startedAt: number;
  } | null>(null);
  const [busyDocument, setBusyDocument] = useState<string | null>(null);
  const [jobPollError, setJobPollError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const uploadLock = useRef(false);

  useEffect(() => {
    let saved: ReturnType<typeof savedSchema.parse> | null = null;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) saved = savedSchema.parse(JSON.parse(raw));
    } catch {
      /* Start clean if this browser's saved schema is invalid. */
    }
    const initial = saved?.conversations.length
      ? saved.conversations
      : [makeConversation()];
    // Browser-only persistence is restored after hydration, never during SSR.
    setConversations(initial);
    setActiveId(
      initial.some((c) => c.id === saved?.activeId)
        ? saved!.activeId
        : initial[0].id,
    );
    setJobs(saved?.jobs ?? []);
    setHydrated(true);
    return () => controller.current?.abort();
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          conversations: conversations
            .slice(0, 30)
            .map((c) => ({ ...c, messages: c.messages.slice(-100) })),
          activeId,
          jobs: jobs.slice(-100),
        }),
      );
    } catch {
      setStorageError(true);
    }
  }, [conversations, activeId, jobs, hydrated]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 5500);
    return () => clearTimeout(timer);
  }, [notice]);

  const refreshDocuments = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await api.documents(signal);
      setDocuments(data.items);
      setDocumentError(null);
    } catch (error) {
      if (!signal?.aborted) setDocumentError(errorText(error));
    } finally {
      if (!signal?.aborted) setLoaded(true);
    }
  }, []);
  const refreshHealth = useCallback(async (signal?: AbortSignal) => {
    try {
      setHealth(await api.health(signal));
    } catch {
      if (!signal?.aborted) setHealth(null);
    }
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    void refreshDocuments(abort.signal);
    void refreshHealth(abort.signal);
    const docsTimer = setInterval(
      () => void refreshDocuments(abort.signal),
      12_000,
    );
    const healthTimer = setInterval(
      () => void refreshHealth(abort.signal),
      30_000,
    );
    return () => {
      abort.abort();
      clearInterval(docsTimer);
      clearInterval(healthTimer);
    };
  }, [refreshDocuments, refreshHealth]);

  const pendingJobKey = jobs
    .filter((j) => j.status === "queued" || j.status === "processing")
    .map((j) => j.job_id)
    .sort()
    .join(",");
  useEffect(() => {
    if (!pendingJobKey) return;
    let alive = true;
    let polling = false;
    async function poll() {
      if (polling) return;
      polling = true;
      const updates = await Promise.all(
        pendingJobKey.split(",").map(async (jobId) => {
          try {
            return await api.job(jobId);
          } catch (error) {
            if (error instanceof ApiError && error.status === 404)
              return {
                job_id: jobId,
                status: "failed" as const,
                error:
                  "This job is no longer available. Reindex the document to try again.",
              };
            return null;
          }
        }),
      );
      polling = false;
      if (!alive) return;
      setJobPollError(updates.some((j) => j === null));
      setJobs((current) =>
        current.map((j) => {
          const update = updates.find((u) => u?.job_id === j.job_id);
          return update ? { ...j, ...update } : j;
        }),
      );
      if (
        updates.some((j) => j?.status === "completed" || j?.status === "failed")
      )
        void refreshDocuments();
    }
    void poll();
    const timer = setInterval(() => void poll(), 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [pendingJobKey, refreshDocuments]);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const indexed = documents.filter((d) => d.status === "indexed");
  const selectedIds = active?.docIds ?? null;
  const available =
    selectedIds === null
      ? indexed
      : indexed.filter((d) => selectedIds.includes(d.id));
  const invalidSelection =
    selectedIds !== null &&
    (selectedIds.length === 0 || available.length !== selectedIds.length);
  const canSend =
    hydrated &&
    loaded &&
    !documentError &&
    !pending &&
    available.length > 0 &&
    !invalidSelection;

  function editConversation(
    id: string,
    update: (item: Conversation) => Conversation,
  ) {
    setConversations((current) =>
      current.map((c) => (c.id === id ? update(c) : c)),
    );
  }
  function newConversation() {
    if (pending) return;
    if (active && active.messages.length === 0) {
      setActiveId(active.id);
      return;
    }
    const next = makeConversation();
    setConversations((current) => [next, ...current].slice(0, 30));
    setActiveId(next.id);
  }
  function chooseConversation(id: string) {
    if (!pending) setActiveId(id);
  }
  function setScope(ids: string[] | null) {
    if (active && !pending)
      editConversation(active.id, (c) => ({ ...c, docIds: ids }));
  }
  function removeConversation(id: string) {
    if (pending) return;
    const remaining = conversations.filter((c) => c.id !== id);
    if (!remaining.length) remaining.push(makeConversation());
    setConversations(remaining);
    if (activeId === id) setActiveId(remaining[0].id);
  }
  function clearHistory() {
    if (pending) return;
    const next = makeConversation();
    setConversations([next]);
    setActiveId(next.id);
    setStorageError(false);
    setNotice("Conversation history cleared from this browser.");
  }
  function trackJob(job: Job) {
    setJobs((current) =>
      [...current.filter((j) => j.document_id !== job.document_id), job].slice(
        -100,
      ),
    );
  }

  async function upload(files: File[]) {
    if (uploadLock.current) return;
    uploadLock.current = true;
    setFileErrors([]);
    try {
      for (const file of files) {
        const validation = validateFile(file);
        if (validation) {
          setFileErrors((current) => [
            ...current,
            { name: file.name, message: validation },
          ]);
          continue;
        }
        setUploading(file.name);
        try {
          trackJob(await api.upload(file));
          await refreshDocuments();
        } catch (error) {
          setFileErrors((current) => [
            ...current,
            { name: file.name, message: errorText(error) },
          ]);
        }
      }
    } finally {
      setUploading(null);
      uploadLock.current = false;
    }
  }
  async function reindex(document: DocumentItem) {
    setBusyDocument(document.id);
    try {
      trackJob(await api.reindex(document.id));
      await refreshDocuments();
      setNotice(
        `Reindexing ${document.name}. You can follow its progress in Documents.`,
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusyDocument(null);
    }
  }
  async function deleteDocument(document: DocumentItem): Promise<boolean> {
    setBusyDocument(document.id);
    try {
      await api.remove(document.id);
      setDocuments((current) => current.filter((d) => d.id !== document.id));
      setJobs((current) =>
        current.filter((j) => j.document_id !== document.id),
      );
      setNotice(`${document.name} was removed from your library.`);
      return true;
    } catch (error) {
      setNotice(errorText(error));
      return false;
    } finally {
      setBusyDocument(null);
    }
  }

  async function send(question: string) {
    const text = question.trim();
    if (
      !text ||
      text.length > 8000 ||
      !active ||
      !canSend ||
      controller.current
    )
      return false;
    const target = active;
    const abort = new AbortController();
    controller.current = abort;
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text,
      createdAt: Date.now(),
    };
    editConversation(target.id, (c) => ({
      ...c,
      messages: [...c.messages, userMessage].slice(-99),
      title: c.messages.length ? c.title : text.slice(0, 65),
      updatedAt: Date.now(),
    }));
    setPending({ conversationId: target.id, startedAt: Date.now() });
    try {
      const answer = await api.chat(
        text,
        target.backendId,
        target.docIds,
        abort.signal,
      );
      const reply: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: answer.answer,
        answer,
        createdAt: Date.now(),
      };
      editConversation(target.id, (c) => ({
        ...c,
        backendId: answer.conversation_id,
        messages: [...c.messages, reply].slice(-100),
        updatedAt: Date.now(),
      }));
    } catch (error) {
      const message = abort.signal.aborted
        ? "You stopped waiting for this answer. The server may still finish processing it."
        : errorText(error);
      const reply: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "",
        error: message,
        createdAt: Date.now(),
      };
      editConversation(target.id, (c) => ({
        ...c,
        ...(error instanceof ApiError && error.status === 404
          ? { backendId: undefined }
          : {}),
        messages: [...c.messages, reply].slice(-100),
      }));
    } finally {
      controller.current = null;
      setPending(null);
    }
    return true;
  }

  return {
    active,
    conversations,
    documents,
    indexed,
    jobs,
    health,
    loaded,
    hydrated,
    documentError,
    storageError,
    notice,
    setNotice,
    uploading,
    fileErrors,
    pending,
    busyDocument,
    jobPollError,
    available,
    invalidSelection,
    canSend,
    refreshDocuments,
    refreshHealth,
    newConversation,
    chooseConversation,
    setScope,
    removeConversation,
    clearHistory,
    upload,
    reindex,
    deleteDocument,
    send,
    cancel: () => controller.current?.abort(),
  };
}
export type WorkspaceState = ReturnType<typeof useWorkspace>;
