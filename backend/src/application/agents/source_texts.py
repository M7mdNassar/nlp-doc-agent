class SourceTexts:
    """Share identical strings without merging document identities or rewriting evidence."""

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}
        self._ids: dict[str, str] = {}

    def add(self, text: str) -> str:
        if text not in self._ids:
            text_id = f"text_{len(self.texts) + 1}"
            self._ids[text] = text_id
            self.texts[text_id] = text
        return self._ids[text]
