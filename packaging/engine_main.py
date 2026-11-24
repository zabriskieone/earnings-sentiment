"""Entry point frozen by PyInstaller into the app's bundled engine."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from earnings_sentiment.server import main

    main()
