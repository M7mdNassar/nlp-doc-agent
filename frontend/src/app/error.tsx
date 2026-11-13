"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="fatal-error">
      <h1>Let’s turn the page.</h1>
      <p>
        The workspace hit an unexpected problem. Your documents are still stored
        in the backend.
      </p>
      <button className="button primary" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
