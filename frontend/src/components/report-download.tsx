"use client";

import { Download, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "@/lib/api";
import type { Answer } from "@/lib/models";
import { Modal } from "./ui";

export function ReportDownload({
  answer,
  content,
  question,
}: {
  answer: Answer;
  content: string;
  question: string;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("Document analysis report");
  const [design, setDesign] = useState("");
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState(false);
  const request = useRef<AbortController | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => () => request.current?.abort(), []);

  function close(next: boolean) {
    setOpen(next);
    if (!next) {
      request.current?.abort();
      setBusy(false);
      setMessage("");
      request.current = null;
      trigger.current?.focus();
    }
  }

  async function download() {
    if (request.current || !title.trim()) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setMessage("");
    setFailure(false);
    try {
      const result = await api.report(
        {
          title: title.trim(),
          design: design.trim(),
          question,
          answer: content,
          sources: answer.sources,
          tool_results: answer.tool_results.map(({ name, output }) => ({
            name,
            output,
          })),
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(result.file);
      const link = document.createElement("a");
      link.href = url;
      link.download = "folio-report.pdf";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (result.design === "standard")
        setMessage(
          "Downloaded with the standard layout. The design agent could not supply a layout.",
        );
      else close(false);
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailure(true);
        setMessage(errorText(error));
      }
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <>
      <button
        ref={trigger}
        className="text-button"
        onClick={() => setOpen(true)}
      >
        <Download size={15} /> PDF report
      </button>
      <Modal
        open={open}
        onOpenChange={close}
        title="Create PDF report"
        description="Export this answer with its sources and analysis results."
      >
        <form
          className="report-form"
          onSubmit={(event) => {
            event.preventDefault();
            void download();
          }}
        >
          <label>
            Report title
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              maxLength={120}
            />
          </label>
          <label>
            Design instructions (optional)
            <textarea
              value={design}
              onChange={(event) => setDesign(event.target.value)}
              rows={3}
              maxLength={1000}
              placeholder="Use a serif font, navy headings, and a compact one-column layout."
            />
          </label>
          {message && <p role={failure ? "alert" : "status"}>{message}</p>}
          <button
            className="button primary"
            type="submit"
            disabled={busy || !title.trim()}
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Download size={15} />
            )}
            {busy ? "Generating PDF…" : "Download PDF"}
          </button>
        </form>
      </Modal>
    </>
  );
}
