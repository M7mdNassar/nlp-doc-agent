"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUpRight,
  Check,
  Copy,
  Database,
  FileSearch,
  RotateCcw,
} from "lucide-react";
import type { Answer, Message, Source } from "@/lib/models";
import { sourceLocation } from "@/lib/models";
import { Brand, FileBadge } from "./ui";
import { ActivityHistory, ToolsUsed } from "./agent-activity";
import { ReportDownload } from "./report-download";

function label(text: string) {
  return text.replace(/[\[\]\r\n]/g, " ").trim();
}

const cacheLabels = {
  miss: {
    label: "Cache miss",
    description: "No saved answer matched this request.",
  },
  exact_hit: {
    label: "Cache hit · Exact",
    description:
      "Reused a verified answer for this exact request. Source quotes checked.",
  },
  semantic_hit: {
    label: "Cache hit · Semantic",
    description:
      "Reused a verified answer for a matching paraphrase. Source quotes checked.",
  },
  bypass: {
    label: "Cache bypassed",
    description: "Cache was not used for this request.",
  },
} as const;

function CacheStatus({ cache }: { cache: Answer["cache"] }) {
  if (!cache) return null;
  const details = cacheLabels[cache.status];
  return (
    <div
      className="cache-status"
      data-cache-status={cache.status}
      role="status"
    >
      <strong className="cache-status-badge">
        <Database size={13} aria-hidden="true" />
        {details.label}
      </strong>
      <span>{details.description}</span>
    </div>
  );
}
export function answerMarkdown(answer: Answer) {
  let text = answer.answer;
  const tables = answer.tool_results.filter(
    (tool) => tool.name === "table_extractor",
  );
  if (
    tables.some(
      ({ output }) =>
        Array.isArray(output.headers) &&
        output.headers.length > 1 &&
        Array.isArray(output.rows) &&
        output.rows.length > 0,
    ) &&
    !tables.some(({ output }) => output.format === "layout")
  ) {
    // Some models fence an otherwise valid Markdown grid. Unwrap only complete
    // table blocks backed by structured extraction; keep code/layout text intact.
    text = text.replace(
      /(^|\n)(`{3,}|~{3,})[ \t]*(?:markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n\2[ \t]*(?=\r?\n|$)/gi,
      (original, newline: string, _fence: string, body: string) => {
        const rows = body.trim().split(/\r?\n/);
        const width = (row: string) =>
          row
            .trim()
            .slice(1, -1)
            .split(/(?<!\\)\|/).length;
        const isTable =
          rows.length >= 3 &&
          /^\s*\|(?:[ \t]*:?-{3,}:?[ \t]*\|){2,}[ \t]*$/.test(rows[1]) &&
          rows.every(
            (row) =>
              /^\s*\|.+\|[ \t]*$/.test(row) && width(row) === width(rows[0]),
          );
        return isTable ? newline + body : original;
      },
    );
  }
  const footer = text.lastIndexOf("\n\nSources:\n");
  if (
    footer >= 0 &&
    answer.sources.length > 0 &&
    answer.sources.every((s) => text.slice(footer).includes(`(${s.chunk_id})`))
  )
    text = text.slice(0, footer);
  const handled = new Set<string>();
  answer.sources.forEach((source, index) => {
    const location = source.location
      ? [source.section, source.location].filter(Boolean).join(", ")
      : `p. ${source.page}`;
    const citation = `[${label(source.document_name)}, ${label(location)}]`;
    if (!handled.has(citation)) {
      text = text
        .split(citation)
        .join(
          `[${index + 1} · ${label(source.document_name)}](#source-${index})`,
        );
      handled.add(citation);
    }
  });
  return text;
}

export function AnswerMessage({
  message,
  question,
  onSource,
  onRetry,
  disabled,
}: {
  message: Message;
  question: string;
  onSource: (sources: Source[], index: number) => void;
  onRetry: () => void;
  disabled: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const answer = message.answer;
  async function copy() {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError(true);
    }
  }
  return (
    <article className="answer-message">
      <div className="answer-avatar">
        <Brand small />
      </div>
      <div className="answer-body">
        <div className="answer-byline">
          <strong>Folio</strong>
          <span>
            {answer?.sources.length
              ? "Grounded in your documents"
              : "Document assistant"}
          </span>
        </div>
        {message.error ? (
          <div className="answer-error" role="alert">
            <p>{message.error}</p>
            <button
              className="text-button"
              onClick={onRetry}
              disabled={disabled}
            >
              <RotateCcw size={14} /> Try again
            </button>
          </div>
        ) : (
          <>
            <CacheStatus cache={answer?.cache} />
            {answer?.state === "insufficient_evidence" && (
              <div className="evidence-notice">
                <FileSearch size={19} />
                <div>
                  <strong>Not enough verified evidence</strong>
                  <p>
                    Try a more specific question, choose different documents, or
                    add another source.
                  </p>
                </div>
              </div>
            )}
            <div className="prose">
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Answers are evidence text; never load model-provided tracking images.
                  img: ({ alt }) => <span>{alt || "Image reference"}</span>,
                  a: ({ href, children }) => {
                    if (href?.startsWith("#source-") && answer) {
                      const index = Number(href.slice(8));
                      if (Number.isInteger(index) && answer.sources[index])
                        return (
                          <button
                            className="inline-citation"
                            onClick={() => onSource(answer.sources, index)}
                          >
                            {children}
                            <ArrowUpRight size={11} />
                          </button>
                        );
                    }
                    return (
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {children}
                      </a>
                    );
                  },
                  table: ({ children }) => (
                    <div className="table-scroll">
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {answer ? answerMarkdown(answer) : message.text}
              </Markdown>
            </div>
            {!!answer?.sources.length && (
              <div className="answer-sources">
                <div className="eyebrow">
                  SOURCES <span>{answer.sources.length}</span>
                </div>
                <div className="source-cards">
                  {answer.sources.map((source, index) => (
                    <button
                      className="source-card"
                      key={source.chunk_id}
                      onClick={() => onSource(answer.sources, index)}
                    >
                      <FileBadge name={source.document_name} small />
                      <span>
                        <strong>{source.document_name}</strong>
                        <small>{sourceLocation(source)}</small>
                      </span>
                      <span className="source-number">{index + 1}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {answer && <ToolsUsed answer={answer} />}
            {!!answer?.activity?.length && (
              <ActivityHistory steps={answer.activity} />
            )}
            <div className="answer-actions">
              <button
                className="icon-button"
                aria-label={copied ? "Answer copied" : "Copy answer"}
                onClick={() => void copy()}
              >
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
              {copied && <span>Copied</span>}
              {copyError && (
                <span role="status">Select the answer text to copy it.</span>
              )}
              {answer?.state === "answer_ready" &&
                answer.sources.length > 0 &&
                question && (
                  <ReportDownload
                    answer={answer}
                    content={answerMarkdown(answer)}
                    question={question}
                  />
                )}
              <time dateTime={new Date(message.createdAt).toISOString()}>
                {new Date(message.createdAt).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
            </div>
          </>
        )}
      </div>
    </article>
  );
}
