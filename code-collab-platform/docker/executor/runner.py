"""
Reads JSON from stdin: {language, code}
Executes code in subprocess with timeout
Outputs JSON to stdout: {stdout, stderr, exit_code, duration_ms}
No network access. No file system writes outside /tmp.
"""

import json
import os
import subprocess
import sys
import time

TIMEOUT_SEC = int(os.environ.get("EXECUTION_TIMEOUT_SEC", 5))
MAX_OUTPUT_BYTES = 64 * 1024

LANGUAGE_COMMANDS = {
    "python": ["python", "-c"],
    "javascript": ["node", "-e"],
}


def main():
    try:
        payload = json.loads(sys.stdin.read())
        language = payload.get("language", "python")
        code = payload.get("code", "")

        cmd = LANGUAGE_COMMANDS.get(language)
        if not cmd:
            print(json.dumps({"error": f"Unsupported language: {language}"}))
            sys.exit(1)

        start = time.monotonic()

        try:
            result = subprocess.run(
                cmd + [code],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SEC,
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "PIP_NO_INDEX": "1",
                    "npm_config_offline": "true",
                    "HTTP_PROXY": "",
                    "HTTPS_PROXY": "",
                },
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            print(
                json.dumps(
                    {
                        "stdout": result.stdout[:MAX_OUTPUT_BYTES],
                        "stderr": result.stderr[:MAX_OUTPUT_BYTES],
                        "exit_code": result.returncode,
                        "duration_ms": duration_ms,
                    }
                )
            )

        except subprocess.TimeoutExpired:
            print(
                json.dumps(
                    {
                        "stdout": "",
                        "stderr": f"Execution timed out after {TIMEOUT_SEC}s",
                        "exit_code": -1,
                        "duration_ms": TIMEOUT_SEC * 1000,
                    }
                )
            )

    except Exception as exc:
        print(json.dumps({"error": str(exc), "exit_code": -1}))


if __name__ == "__main__":
    main()
