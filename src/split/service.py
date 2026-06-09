import os
import uuid

from pypdf import PdfReader, PdfWriter


def get_page_count(path: str) -> int:
    return len(PdfReader(path).pages)


def split_pdf(source_path: str, split_pages: list[int], uploads_dir: str) -> list[str]:
    reader = PdfReader(source_path)
    total = len(reader.pages)

    sorted_pages = sorted(split_pages)
    starts = [p - 1 for p in sorted_pages]
    ends = starts[1:] + [total]

    paths = []
    for start, end in zip(starts, ends):
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        path = os.path.join(uploads_dir, f"{uuid.uuid4()}.pdf")
        with open(path, "wb") as f:
            writer.write(f)
        paths.append(path)
    return paths
