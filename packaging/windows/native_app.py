"""Private, frozen Native-only entry point; never install or repair Python/NI."""
from multiprocessing import freeze_support
from spitfire.frozen import main

if __name__ == '__main__':
    freeze_support()
    raise SystemExit(main())
