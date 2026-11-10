"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUpRight,
  Calculator,
  Check,
  ChevronDown,
  Copy,
  FileSearch,
  RotateCcw,
} from "lucide-react";
import type { Answer, Message, Source } from "@/lib/models";
import { sourceLocation } from "@/lib/models";
import { Brand, FileBadge } from "./ui";

function label(text: string) {
  return text.replace(/[\[\]\r\n]/g, " ").trim();
}
export function answerMarkdown(answer: Answer) {
  let text = answer.answer;
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
  onSource,
  onRetry,
  disabled,
}: {
  message: Message;
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
            {!!answer?.tool_results.length && (
              <details className="tool-details">
                <summary>
                  <Calculator size={14} />{" "}
                  {answer.tool_results.length === 1
                    ? "Analysis details"
                    : `${answer.tool_results.length} analysis steps`}
                  <ChevronDown size={14} />
                </summary>
                {answer.tool_results.map((tool, index) => (
                  <div key={index}>
                    <strong>{tool.name.replaceAll("_", " ")}</strong>
                    {tool.output.result !== undefined && (
                      <p>
                        Result: <b>{String(tool.output.result)}</b>
                      </p>
                    )}
                    <pre>{JSON.stringify(tool.output, null, 2)}</pre>
                  </div>
                ))}
              </details>
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
