from .texlive import TexLive as _TexLive

texlive = _TexLive(
    name="TeX Live",
    version="",
    description="LaTeX typesetting system",
    website="https://www.tug.org/texlive/",
)

__all__ = ["texlive"]

