"""CLI tool to parse/convert SIMAL files."""

import argparse
import json
from pathlib import Path

from simal_conversion import system_to_json_dict, system_to_simple_json_dict
from simal_normalize import remove_leading_indentation
from simal_parser import parse_dsl


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse SIMAL and convert to JSON formats.")
    parser.add_argument("path", help="Path to a .siml/.simal schema file")
    parser.add_argument(
        "--dedent-out",
        dest="dedent_out",
        default=None,
        help=(
            "Write a dedented copy of the input schema to the given path (file or directory). "
            "Leading spaces/tabs are removed per line; newlines are preserved; heredoc bodies are preserved."
        ),
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit full JSON (<name>.json)",
    )
    parser.add_argument(
        "--simple",
        dest="emit_simple",
        action="store_true",
        help="Emit simplified JSON (<name>_simple.json)",
    )
    parser.add_argument(
        "--max-simple",
        action="store_true",
        help="Emit max-simplified JSON (<name>_max_simple.json)",
    )

    parser.add_argument(
        "--merge-duplicate-attrs",
        dest="merge_duplicate_attrs",
        action="store_true",
        default=True,
        help="Merge duplicate attribute keys (default: on). List values concatenate; dict values shallow-merge.",
    )
    parser.add_argument(
        "--no-merge-duplicate-attrs",
        dest="merge_duplicate_attrs",
        action="store_false",
        help="Disable merging duplicate attribute keys; later occurrences overwrite earlier ones.",
    )

    args = parser.parse_args()
    path = args.path
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if args.dedent_out:
        out_target = Path(args.dedent_out)
        in_path = Path(path)
        treat_as_dir = (
            (out_target.exists() and out_target.is_dir())
            or str(args.dedent_out).endswith(("/", "\\"))
        )
        out_path = (out_target / in_path.name) if treat_as_dir else out_target
        out_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = remove_leading_indentation(content, preserve_heredocs=True)
        out_path.write_text(normalized, encoding="utf-8")
    try:
        system = parse_dsl(content, merge_duplicate_attrs=args.merge_duplicate_attrs)
    except Exception as e:
        raise SystemExit(f"Error parsing SIMAL file: {e}")

    # if no output flags are provided, emit json + simplified json by default
    any_flag = args.emit_json or args.emit_simple or args.max_simple
    emit_json = args.emit_json or not any_flag
    emit_simple = args.emit_simple or not any_flag

    if emit_json:
        as_dict = system_to_json_dict(system)
        json_path = ".".join(path.split(".")[:-1]) + ".json"
        with open(json_path, "w", encoding="utf-8") as fw:
            json.dump(as_dict, fw, indent=4)

    if emit_simple:
        as_dict = system_to_simple_json_dict(system)
        simple_json_path = ".".join(path.split(".")[:-1]) + "_simple.json"
        with open(simple_json_path, "w", encoding="utf-8") as fw:
            json.dump(as_dict, fw, indent=4)

    if args.max_simple:
        as_dict = system_to_simple_json_dict(system, max_simplify=True)
        max_simple_json_path = ".".join(path.split(".")[:-1]) + "_max_simple.json"
        with open(max_simple_json_path, "w", encoding="utf-8") as fw:
            json.dump(as_dict, fw, indent=4)
