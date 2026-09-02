import argparse
import json
from pathlib import Path

from truss_api.core.settings import get_settings
from truss_api.db.schema import initialize_database
from truss_api.recovery.backup import create_backup, verify_backup
from truss_api.recovery.diagnostics import run_diagnostics
from truss_api.recovery.errors import TrussError
from truss_api.recovery.restore import restore_backup


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recuperacao local segura do Truss")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup-create")
    create.add_argument("--output", type=Path)
    verify = commands.add_parser("backup-verify")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--target", type=Path, required=True)
    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("--deep", action="store_true")
    resume = commands.add_parser("resume")
    resume.add_argument("operation_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "backup-create":
            path = create_backup(settings, args.output)
            print(json.dumps({"status": "ok", "archive": str(path)}, ensure_ascii=False))
        elif args.command == "backup-verify":
            manifest = verify_backup(args.archive)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "backup_id": manifest["backup_id"],
                        "files": len(manifest["files"]),
                        "total_size_bytes": manifest["total_size_bytes"],
                    },
                    ensure_ascii=False,
                )
            )
        elif args.command == "restore":
            target = restore_backup(args.archive, args.target)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "target": str(target),
                        "next": f"$env:TRUSS_DATA_DIR='{target}'",
                    },
                    ensure_ascii=False,
                )
            )
        elif args.command == "diagnose":
            print(json.dumps(run_diagnostics(settings, deep=args.deep), ensure_ascii=False))
        elif args.command == "resume":
            # Import lazy: os modulos de PDF nao devem emitir warnings antes do JSON
            # dos comandos de backup, verify, restore ou diagnose.
            from truss_api.recovery.operations import resume_operation

            initialize_database(settings)
            print(json.dumps(resume_operation(args.operation_id, settings), ensure_ascii=False))
    except TrussError as error:
        print(json.dumps({"status": "error", "detail": error.public.as_detail()}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
