import React from "react";

export interface CitationMatch {
  docId: string;
  page: number;
  raw: string;
}

// Matches [doc_1234, p. 12] or [doc_1234, p.12]
const CITATION_REGEX = /\[(doc_[a-fA-F0-9]+),\s*p\.\s*(\d+)\]/g;

export function extractCitations(text: string): CitationMatch[] {
  const matches: CitationMatch[] = [];
  let match;
  while ((match = CITATION_REGEX.exec(text)) !== null) {
    matches.push({
      docId: match[1],
      page: parseInt(match[2], 10),
      raw: match[0],
    });
  }
  // Reset regex state
  CITATION_REGEX.lastIndex = 0;
  return matches;
}

export function formatTextWithCitations(
  text: string, 
  onCitationClick: (citation: CitationMatch) => void
): React.ReactNode[] {
  const parts = text.split(CITATION_REGEX);
  // The split creates an array: [text, docId, page, text, docId, page, text...]
  const result: React.ReactNode[] = [];
  
  for (let i = 0; i < parts.length; i++) {
    if (i % 3 === 0) {
      // Normal text
      if (parts[i]) result.push(parts[i]);
    } else if (i % 3 === 1) {
      // Doc ID and Page number
      const docId = parts[i];
      const page = parts[i + 1];
      const raw = `[${docId}, p. ${page}]`;
      
      result.push(
        React.createElement('button', {
          key: `cite-${i}`,
          onClick: () => onCitationClick({ docId, page: parseInt(page), raw }),
          className: "inline-flex items-center gap-1 mx-1 px-2 py-0.5 text-xs font-medium text-teal-700 bg-teal-50 border border-teal-200 rounded-md hover:bg-teal-100 transition-colors align-baseline",
          title: `Document: ${docId}`
        }, `p. ${page}`)
      );
      i++; // Skip the page number in the next iteration
    }
  }
  return result;
}