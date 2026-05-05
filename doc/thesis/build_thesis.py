from __future__ import annotations

import argparse
from pathlib import Path

import typst


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the Hachi thesis Typst project.")
    parser.add_argument(
        "-o",
        "--output",
        default="Hachi-Thesis.pdf",
        help="Output PDF path, relative to this directory unless absolute.",
    )
    parser.add_argument(
        "--font-path",
        action="append",
        default=[],
        help="Additional font directory. Can be passed more than once.",
    )
    args = parser.parse_args()

    thesis_dir = Path(__file__).resolve().parent
    output = Path(args.output)
    if not output.is_absolute():
        output = thesis_dir / output

    font_paths = [Path(path).expanduser() for path in args.font_path]
    bundled_fonts = thesis_dir / "fonts" / "fonts"
    if bundled_fonts.exists():
        font_paths.append(bundled_fonts)

    compile_kwargs = {}
    if font_paths:
        compile_kwargs["font_paths"] = [str(path) for path in font_paths]

    typst.compile(str(thesis_dir / "main.typ"), output=str(output), **compile_kwargs)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
