import { z } from "zod";

export const documentSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(["queued", "parsing", "embedding", "indexed", "failed"]),
});
export const documentListSchema = z.object({ items: z.array(documentSchema) });
export const jobSchema = z.object({
  job_id: z.string(),
  document_id: z.string(),
  status: z.enum(["queued", "processing", "completed", "failed"]),
  error: z.string().nullable().optional(),
  updated_at: z.string().optional(),
});
export const sourceSchema = z.object({
  chunk_id: z.string(),
  document_id: z.string(),
  document_name: z.string(),
  page: z.number(),
  section: z.string().nullable(),
  location: z.string().nullable(),
  quote: z.string(),
});
export const toolSchema = z.object({
  name: z.string(),
  output: z.record(z.string(), z.unknown()),
  chunk_ids: z.array(z.string()),
});
export const answerSchema = z.object({
  answer: z.string(),
  state: z.enum(["answer_ready", "insufficient_evidence"]),
  loops: z.number(),
  evidence_count: z.number(),
  sources: z.array(sourceSchema),
  tool_results: z.array(toolSchema),
  conversation_id: z.string(),
});
export const healthSchema = z.object({
  status: z.string(),
  dependencies: z.record(z.string(), z.string()),
});
export const messageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  text: z.string(),
  answer: answerSchema.optional(),
  error: z.string().optional(),
  createdAt: z.number(),
});
export const conversationSchema = z.object({
  id: z.string(),
  title: z.string(),
  messages: z.array(messageSchema).max(100),
  backendId: z.string().optional(),
  docIds: z.array(z.string()).max(30).nullable(),
  updatedAt: z.number(),
});
export const savedSchema = z.object({
  conversations: z.array(conversationSchema).max(30),
  activeId: z.string().nullable(),
  jobs: z.array(jobSchema).max(100).default([]),
});
export type DocumentItem = z.infer<typeof documentSchema>;
export type Job = z.infer<typeof jobSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Answer = z.infer<typeof answerSchema>;
export type Message = z.infer<typeof messageSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type Health = z.infer<typeof healthSchema>;
export const STORAGE_KEY = "folio.workspace.v1";
export const MAX_FILE_BYTES = 50 * 1024 * 1024;
export function makeConversation(docIds: string[] | null = null): Conversation {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    messages: [],
    docIds,
    updatedAt: Date.now(),
  };
}
export function sourceLocation(source: Source) {
  if (source.location)
    return [source.section, source.location].filter(Boolean).join(" · ");
  return /\.pdf$/i.test(source.document_name)
    ? `Page ${source.page}`
    : source.section || "Source excerpt";
}
export function fileKind(name: string) {
  return name.split(".").pop()?.toUpperCase() || "FILE";
}
export function validateFile(file: File): string | null {
  if (!/\.(pdf|docx|txt|md)$/i.test(file.name))
    return "Choose a PDF, Word (.docx), text, or Markdown file.";
  if (file.size === 0) return "This file is empty. Choose a file with content.";
  if (file.size > MAX_FILE_BYTES) return "This file is larger than 50 MB.";
  return null;
}
