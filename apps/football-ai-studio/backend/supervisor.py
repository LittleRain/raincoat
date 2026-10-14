"""Terminate a video process if its owning worker exits, including SIGKILL.

The parent owns the write end of a lifeline pipe. EOF means the parent died.
This keeps a restarted server from overlapping an orphan FFmpeg job.
"""
import os
import select
import signal
import subprocess
import sys


def main():
    lifeline = int(sys.argv[1])
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    process = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL)
    try:
        while process.poll() is None:
            ready, _, _ = select.select([lifeline], [], [], .1)
            if stopped or (ready and not os.read(lifeline, 1)):
                return 130
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        os.close(lifeline)


if __name__ == '__main__':
    sys.exit(main())
