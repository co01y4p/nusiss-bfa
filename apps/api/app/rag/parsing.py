import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path


class DocumentParsingError(Exception):
    pass


@dataclass
class DocumentSection:
    heading: str
    content: str


@dataclass
class ParsedDocument:
    title: str
    source_path: str
    content_hash: str
    raw_text: str
    sections: list[DocumentSection] = field(default_factory=list)


class DocumentParser:
    ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}

    def parse_file(
        self, file_path: str | Path, title_override: str | None = None
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        if not path.is_file():
            raise DocumentParsingError(f"File does not exist: {path}")

        suffix = path.suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            raise DocumentParsingError(f"Unsupported file type: '{suffix}'. Allowed: {allowed}")

        raw_bytes = path.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        if suffix == ".pdf":
            raw_text = self._parse_pdf(raw_bytes)
            sections = self._parse_generic_text(raw_text)
            title = (
                title_override
                or self._extract_title_from_text(raw_text)
                or path.stem.replace("-", " ").title()
            )
        elif suffix == ".md":
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            title, sections = self._parse_markdown(raw_text, path.stem)
            if title_override:
                title = title_override
        else:  # .txt
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            sections = self._parse_generic_text(raw_text)
            title = (
                title_override
                or self._extract_title_from_text(raw_text)
                or path.stem.replace("-", " ").title()
            )

        return ParsedDocument(
            title=title,
            source_path=str(path),
            content_hash=content_hash,
            raw_text=raw_text,
            sections=sections,
        )

    def _parse_pdf(self, raw_bytes: bytes) -> str:
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except ImportError:
            # Fallback basic text extraction from PDF stream if pypdf is not installed
            text_matches = re.findall(rb"\(([^\(\)]+)\)\s*Tj", raw_bytes)
            if text_matches:
                return "\n".join(
                    m.decode("latin1", errors="ignore") for m in text_matches
                ).strip()
            # If plain ascii bytes contain text
            ascii_text = "".join(
                chr(b) if 32 <= b <= 126 or b in (10, 13) else " " for b in raw_bytes
            )
            cleaned = re.sub(r"\s+", " ", ascii_text).strip()
            if len(cleaned) > 50:
                return cleaned
            raise DocumentParsingError(
                "PDF parsing requires 'pypdf' package. Please install pypdf or use Markdown/Text."
            ) from None

    def _parse_markdown(self, text: str, fallback_title: str) -> tuple[str, list[DocumentSection]]:
        lines = text.splitlines()
        extracted_title = ""
        sections: list[DocumentSection] = []
        current_heading = ""
        current_lines: list[str] = []

        for line in lines:
            header_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if header_match:
                level = len(header_match.group(1))
                heading_text = header_match.group(2).strip()

                if level == 1 and not extracted_title:
                    extracted_title = heading_text

                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append(
                            DocumentSection(
                                heading=current_heading or extracted_title or fallback_title,
                                content=content,
                            )
                        )
                    current_lines = []
                current_heading = heading_text
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(
                    DocumentSection(
                        heading=current_heading or extracted_title or fallback_title,
                        content=content,
                    )
                )

        if not sections and text.strip():
            sections.append(DocumentSection(heading=fallback_title, content=text.strip()))

        final_title = extracted_title or fallback_title.replace("-", " ").title()
        return final_title, sections

    def _parse_generic_text(self, text: str) -> list[DocumentSection]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        sections: list[DocumentSection] = []
        for i, para in enumerate(paragraphs, start=1):
            sections.append(DocumentSection(heading=f"Section {i}", content=para))
        return sections

    def _extract_title_from_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) < 100:
                return first_line.lstrip("#").strip()
        return ""
