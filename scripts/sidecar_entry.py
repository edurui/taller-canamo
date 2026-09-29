"""PyInstaller entry point; no relative imports from a script package."""
import sys

if __name__ == "__main__":
    release_flags = {"--verify-release-evidence", "--install-release-evidence"}
    if any(argument.split("=", 1)[0] in release_flags for argument in sys.argv[1:]):
        # Read-only verification / explicit dossier installation must not start
        # App, migrate a database, run reminders or create a shutdown backup.
        from taller.release_tools import main
        raise SystemExit(main())
    else:
        from taller.stdio import main
        main()
