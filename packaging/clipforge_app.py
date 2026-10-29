"""Entry point for the installed desktop app (used by PyInstaller)."""
import multiprocessing

from clipforge.desktop import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
