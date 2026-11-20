"use client";

import { LoaderCircle, Mic, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "@/lib/api";

const FORMATS = [
  ["audio/webm;codecs=opus", "webm"],
  ["audio/mp4", "mp4"],
  ["audio/ogg;codecs=opus", "ogg"],
] as const;
const PERMISSION_TIMEOUT_MS = 20_000;

function releaseMicrophone(stream?: MediaStream) {
  stream?.getTracks().forEach((track) => track.stop());
}

function requestMicrophone(signal: AbortSignal): Promise<MediaStream> {
  const access = navigator.mediaDevices.getUserMedia({ audio: true });
  return new Promise((resolve, reject) => {
    let waiting = true;
    const timer = setTimeout(() => {
      fail(
        new DOMException("Microphone permission timed out.", "TimeoutError"),
      );
    }, PERMISSION_TIMEOUT_MS);

    function finish() {
      waiting = false;
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
    function fail(error: unknown) {
      if (!waiting) return;
      finish();
      reject(error);
    }
    function abort() {
      fail(signal.reason);
    }

    signal.addEventListener("abort", abort, { once: true });
    void access.then((stream) => {
      if (!waiting) {
        // The browser can grant access after Folio cancels its wait.
        releaseMicrophone(stream);
        return;
      }
      finish();
      resolve(stream);
    }, fail);
  });
}

function microphoneError(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case "TimeoutError":
        return "Microphone permission timed out. Check the site controls beside the address bar, allow the microphone, then try again.";
      case "NotAllowedError":
      case "SecurityError":
        return "Microphone access was blocked. Allow it in your browser’s site settings and check your system microphone permissions.";
      case "NotFoundError":
        return "No microphone was found. Connect a microphone and try again.";
      case "NotReadableError":
        return "Could not open the microphone. Check your system input settings and close any apps using it.";
    }
  }
  return errorText(error);
}

export function VoiceQuery({
  disabled,
  onTranscript,
}: {
  disabled: boolean;
  onTranscript: (text: string) => void;
}) {
  const [phase, setPhase] = useState<
    "idle" | "permission" | "recording" | "transcribing"
  >("idle");
  const [message, setMessage] = useState("");
  const session = useRef<AbortController | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);

  useEffect(() => () => session.current?.abort(), []);

  function cancelPermission() {
    session.current?.abort();
    setPhase("idle");
    setMessage("Microphone request canceled.");
  }

  async function record() {
    if (session.current) return;
    setMessage("");
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setMessage(
        "Microphone recording requires a supported browser on localhost or HTTPS.",
      );
      return;
    }
    const format = FORMATS.find(([mime]) =>
      MediaRecorder.isTypeSupported(mime),
    );
    if (!format) {
      setMessage(
        "This browser does not support a compatible recording format.",
      );
      return;
    }
    const controller = new AbortController();
    const { signal } = controller;
    session.current = controller;
    setPhase("permission");
    let stream: MediaStream | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      stream = await requestMicrophone(signal);
      if (signal.aborted) return;
      const media = new MediaRecorder(stream, {
        mimeType: format[0],
        audioBitsPerSecond: 64000,
      });
      recorder.current = media;
      const chunks: Blob[] = [];
      const stop = () => {
        if (media.state !== "inactive") media.stop();
      };
      const recording = new Promise<Blob>((resolve, reject) => {
        media.ondataavailable = (event) => {
          if (event.data.size) chunks.push(event.data);
        };
        media.onstop = () =>
          resolve(new Blob(chunks, { type: media.mimeType || format[0] }));
        media.onerror = () =>
          reject(new Error("The microphone stopped unexpectedly."));
        signal.addEventListener("abort", stop, { once: true });
        media.start();
      });
      timer = setTimeout(stop, 45_000);
      setPhase("recording");
      const audio = await recording;
      signal.removeEventListener("abort", stop);
      releaseMicrophone(stream);
      stream = undefined;
      if (signal.aborted) return;
      if (!audio.size) throw new Error("No audio was recorded. Try again.");
      setPhase("transcribing");
      const { text } = await api.transcribe(
        new File([audio], `question.${format[1]}`, { type: audio.type }),
        signal,
      );
      if (signal.aborted) return;
      onTranscript(text);
      setMessage("Review the transcript, then send your question.");
    } catch (error) {
      if (!signal.aborted) setMessage(microphoneError(error));
    } finally {
      clearTimeout(timer);
      releaseMicrophone(stream);
      recorder.current = null;
      session.current = null;
      if (!signal.aborted) setPhase("idle");
    }
  }

  const label =
    phase === "permission"
      ? "Cancel microphone request"
      : phase === "recording"
        ? "Stop recording"
        : "Record a question";

  return (
    <div className="voice-query">
      <button
        type="button"
        className="icon-button"
        title={
          phase === "idle" ? "Record a question (transcribed by Groq)" : label
        }
        aria-label={label}
        disabled={phase === "transcribing" || (phase === "idle" && disabled)}
        onClick={() => {
          if (phase === "permission") cancelPermission();
          else if (phase === "recording") {
            if (recorder.current?.state !== "inactive")
              recorder.current?.stop();
          } else void record();
        }}
      >
        {phase === "permission" ? (
          <X size={17} />
        ) : phase === "recording" ? (
          <Square size={16} />
        ) : phase === "idle" ? (
          <Mic size={17} />
        ) : (
          <LoaderCircle size={17} />
        )}
      </button>
      <span className="voice-status" role="status">
        {phase === "recording"
          ? "Recording · up to 45 seconds"
          : phase === "permission"
            ? "Waiting for microphone permission… Check the site controls beside the address bar if no prompt appears."
            : phase === "transcribing"
              ? "Transcribing with Groq…"
              : message}
      </span>
    </div>
  );
}
