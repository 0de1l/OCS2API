"""Check a running OCS2API service without making paid upstream requests."""

import argparse
import json
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    try:
        with urllib.request.urlopen(args.url.rstrip("/") + "/api/health", timeout=5) as response:
            data = json.load(response)
        if data.get("status") != "ok":
            raise ValueError("Unexpected health response")
        print("OCS2API health: OK")
        return 0
    except (OSError, ValueError):
        print("Health check failed. Check the process, port and URL.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
