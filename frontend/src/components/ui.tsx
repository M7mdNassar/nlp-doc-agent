"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Check, FileText, LoaderCircle, X } from "lucide-react";
import type { ReactNode } from "react";
import type { DocumentItem } from "@/lib/models";
import { fileKind } from "@/lib/models";

export function Brand({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand ${small ? "brand-small" : ""}`}>
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {!small && (
        <span>
          folio<span className="brand-period">.</span>
        </span>
      )}
    </span>
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
  drawer = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
  drawer?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className={`modal ${wide ? "modal-wide" : ""} ${drawer ? "source-drawer" : ""}`}
          {...(!description ? { "aria-describedby": undefined } : {})}
        >
          <div className="modal-heading">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              {description && (
                <Dialog.Description>{description}</Dialog.Description>
              )}
            </div>
            <Dialog.Close className="icon-button" aria-label="Close dialog">
              <X size={19} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function FileBadge({
  name,
  small = false,
}: {
  name: string;
  small?: boolean;
}) {
  const kind = fileKind(name);
  return (
    <span
      className={`file-badge file-${kind.toLowerCase()} ${small ? "file-small" : ""}`}
      aria-hidden="true"
    >
      <FileText size={small ? 17 : 22} />
      {!small && <span>{kind}</span>}
    </span>
  );
}
export function StatusBadge({ status }: { status: DocumentItem["status"] }) {
  return (
    <span className={`status-badge status-${status}`}>
      {status === "indexed" ? (
        <Check size={12} />
      ) : status !== "failed" ? (
        <LoaderCircle size={12} className="spin" />
      ) : (
        <span className="status-dot" />
      )}
      {
        {
          indexed: "Ready",
          queued: "Queued",
          parsing: "Reading",
          embedding: "Indexing",
          failed: "Needs attention",
        }[status]
      }
    </span>
  );
}
