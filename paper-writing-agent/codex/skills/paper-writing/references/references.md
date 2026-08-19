# Reference protocol

Apply this protocol only to references not already backed by a valid project registry and unchanged
hashes.

1. Search the internet for an arXiv version. Confirm title, authors, and abstract on the abs page.
2. Download the complete source archive from `https://arxiv.org/e-print/<id>`.
3. Save the raw archive and SHA-256. Extract with `paperctl safe-extract-arxiv ARCHIVE DEST` into
   `PROJECT/refs/<id-with-underscores>/`. The command refuses existing destinations, traversal,
   links, devices, and oversized archives.
4. Follow `\input`/`\include` and inspect the actual TeX for the exact result being cited. Record the
   file, line/window or excerpt hash, claim, and decision. An abstract is discovery evidence only.
5. If the content is present, commit to cite it. Otherwise mark the candidate rejected and verify a
   similar arXiv paper. If no arXiv version exists, use a similar paper with a verifiable arXiv source;
   for books, use the campaign's public-copy protocol and escalate if none is available.
6. Open “Export BibTeX citation” on the arXiv abs page. Save that block verbatim and its SHA-256;
   never hand-write an arXiv BibTeX entry.

Each arXiv `references-registry.json` entry needs `source_type: arxiv`, citation key, arXiv ID, canonical URLs, confirmed title,
authors, abstract confirmation, raw archive path/hash, extracted source directory, relevant TeX
location/evidence hash, exact supported claim, accepted/rejected status, BibTeX snapshot path/hash,
the candidate bibliography path, and verification date. Reuse cached material only when these paths
and hashes agree. A book fallback uses `source_type: book`, a public URL, local public source
file/hash, evidence file/page/hash, exact claim, saved citation snapshot/hash, candidate bibliography
path, and verification date; it does not pretend to have arXiv fields.
