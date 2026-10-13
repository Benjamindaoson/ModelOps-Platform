"""Immutable SmolVLA model registry operations for one authorized Linux host."""
import argparse
import json
from pathlib import Path

from pipelines.robotics.adapter import Registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("register", "resolve", "deploy", "rollback"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args()
    registry = Registry(args.root)
    if args.operation == "register":
        if args.record is None:
            parser.error("register requires --record")
        result = registry.register(json.loads(args.record.read_text()))
    elif args.operation == "resolve":
        result = registry.resolve(args.version)
    elif args.operation == "deploy":
        if args.evaluation is None:
            parser.error("deploy requires --evaluation")
        result = registry.deploy(args.version, json.loads(args.evaluation.read_text()))
    else:
        result = registry.rollback(args.version)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
