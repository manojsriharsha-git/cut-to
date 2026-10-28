"""Command-line entry for Phase 1.

    python -m app.cli convert samples/sample.fountain out/sample.fdx
    python -m app.cli info samples/sample.fountain
"""
import argparse
import sys
from collections import Counter

from .formats import load, save


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="screenplay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="convert between .fountain/.fdx/.json")
    c.add_argument("src")
    c.add_argument("dst")
    i = sub.add_parser("info", help="print scene/character stats")
    i.add_argument("src")
    args = ap.parse_args(argv)

    script = load(args.src)
    if args.cmd == "convert":
        save(script, args.dst)
        print(f"Wrote {args.dst}  ({len(script.elements)} elements)")
    else:
        counts = Counter(e.type for e in script.elements)
        print(f"Title: {script.title() or '(none)'}")
        print(f"Scenes: {len(script.scenes())}")
        print(f"Characters: {', '.join(script.characters())}")
        for t, n in counts.most_common():
            print(f"  {t:<15} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
