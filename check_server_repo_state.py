import argparse
import getpass
import os
import posixpath
import shlex
import socket
import sys
import time
from pathlib import Path
from textwrap import dedent

try:
    import paramiko
except ImportError as exc:
    paramiko = None
    PARAMIKO_IMPORT_ERROR = exc
else:
    PARAMIKO_IMPORT_ERROR = None


DEFAULT_REMOTE_CANDIDATES = (
    "/opt/perf_commissions",
    "/opt/Perf-Commission",
    "/opt/Perf_commissions",
    "/opt/lka_automations",
)
DEFAULT_API_SYNC_FILES = (
    "api.py",
    "docker-compose.yml",
    "Dockerfile.api",
    "requirements-api.txt",
)
ROOT = Path(__file__).resolve().parent


def log(message: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect and diagnose the remote Perf Commissions API over SSH."
    )
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-pass")
    parser.add_argument("--remote-dir", default="/opt/perf_commissions")
    parser.add_argument("--opt-root", default="/opt")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--sample-id", default="TEST123")
    parser.add_argument("--public-base-url")
    parser.add_argument("--retry-minutes", type=int, default=5)
    parser.add_argument("--retry-interval", type=int, default=10)
    parser.add_argument("--connect-timeout", type=int, default=12)
    parser.add_argument("--command-timeout", type=int, default=600)
    parser.add_argument("--http-retries", type=int, default=5)
    parser.add_argument("--http-delay", type=int, default=2)
    parser.add_argument("--upload-api-files", action="store_true")
    parser.add_argument("--upload-path", action="append", default=[])
    parser.add_argument("--rebuild-api", action="store_true")
    parser.add_argument("--sync-running-container", action="store_true")
    parser.add_argument("--rebuild-log-lines", type=int, default=120)
    parser.add_argument("--skip-diagnosis", action="store_true")
    return parser.parse_args()


def shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def resolve_public_base_url(args) -> str:
    if args.public_base_url:
        return args.public_base_url.rstrip("/")

    host = args.ssh_host.strip()
    if ":" in host and not host.startswith("[") and host.count(":") > 1:
        host = f"[{host}]"
    return f"http://{host}:{args.api_port}"


def connect_with_retry(args):
    deadline = time.monotonic() + (args.retry_minutes * 60)
    attempt = 1
    last_error = None

    while True:
        remaining_seconds = int(deadline - time.monotonic())
        if remaining_seconds <= 0:
            raise TimeoutError(
                f"SSH API diagnosis did not succeed within {args.retry_minutes} minute(s). "
                f"Last error: {last_error.__class__.__name__}: {last_error}"
            ) from last_error

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            log(
                f"SSH attempt {attempt} to {args.ssh_user}@{args.ssh_host}:{args.ssh_port} "
                f"({remaining_seconds}s remaining)"
            )
            client.connect(
                hostname=args.ssh_host,
                port=args.ssh_port,
                username=args.ssh_user,
                password=args.ssh_pass,
                timeout=args.connect_timeout,
                auth_timeout=args.connect_timeout,
                banner_timeout=args.connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            log("SSH connection established.")
            return client
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError, socket.timeout) as exc:
            last_error = exc
            client.close()
            wait_seconds = min(args.retry_interval, max(1, remaining_seconds))
            log(f"SSH not ready yet: {exc.__class__.__name__}: {exc}. Retrying in {wait_seconds}s.")
            time.sleep(wait_seconds)
            attempt += 1


def run_remote_command(client, command: str, timeout: int = 90, stream: bool = False):
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    channel = stdout.channel
    start_time = time.monotonic()
    output_chunks = []
    error_chunks = []

    while True:
        made_progress = False

        while channel.recv_ready():
            data = channel.recv(4096).decode("utf-8", errors="replace")
            output_chunks.append(data)
            if stream:
                sys.stdout.write(data)
                sys.stdout.flush()
            made_progress = True

        while channel.recv_stderr_ready():
            data = channel.recv_stderr(4096).decode("utf-8", errors="replace")
            error_chunks.append(data)
            if stream:
                sys.stderr.write(data)
                sys.stderr.flush()
            made_progress = True

        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break

        if timeout and (time.monotonic() - start_time) > timeout:
            channel.close()
            raise TimeoutError(f"Remote command exceeded {timeout} second(s).")

        if not made_progress:
            time.sleep(0.2)

    exit_status = channel.recv_exit_status()
    return exit_status, "".join(output_chunks), "".join(error_chunks)


def resolve_remote_dir_on_server(client, args) -> str:
    candidate_args = " ".join(
        shell_quote(path)
        for path in dict.fromkeys([args.remote_dir, *DEFAULT_REMOTE_CANDIDATES])
    )
    command = dedent(
        """\
        set +e
        INPUT_REMOTE_DIR=__INPUT_REMOTE_DIR__
        OPT_ROOT=__OPT_ROOT__

        if [ -d "$INPUT_REMOTE_DIR" ]; then
            printf '%s\n' "$INPUT_REMOTE_DIR"
            exit 0
        fi

        for candidate in __CANDIDATE_ARGS__; do
            if [ -d "$candidate" ]; then
                printf '%s\n' "$candidate"
                exit 0
            fi
        done

            find "$OPT_ROOT" -maxdepth 2 -type d \\( -name '*perf*' -o -name '*commission*' -o -name '*lka*' \\) 2>/dev/null | while IFS= read -r dir; do
            if [ -f "$dir/api.py" ] || [ -f "$dir/docker-compose.yml" ] || [ -f "$dir/run_server.sh" ]; then
                printf '%s\n' "$dir"
                exit 0
            fi
        done
        """
    )
    command = (
        command
        .replace("__INPUT_REMOTE_DIR__", shell_quote(args.remote_dir))
        .replace("__OPT_ROOT__", shell_quote(args.opt_root))
        .replace("__CANDIDATE_ARGS__", candidate_args)
    )

    exit_status, output, errors = run_remote_command(client, command, timeout=60)
    if errors.strip():
        log(f"Remote directory resolution stderr: {errors.strip()}")

    candidates = [line.strip() for line in output.splitlines() if line.strip()]
    if exit_status != 0 or not candidates:
        raise FileNotFoundError(
            f"Could not resolve the remote app directory under {args.opt_root}."
        )

    return candidates[-1]


def build_remote_container_sync_command(remote_dir: str, relative_paths: list[str], log_lines: int) -> str:
    file_list = "\n".join(path.replace("\\", "/") for path in relative_paths)
    template = dedent(
        """\
        set -e
        REMOTE_DIR=__REMOTE_DIR__
        LOG_LINES=__LOG_LINES__
        CONTAINER_NAME=lka_perf_api
        APP_ROOT=/app

        container_id="$(docker ps -aqf name=$CONTAINER_NAME | head -n 1)"
        if [ -z "$container_id" ]; then
            echo ERROR=container_not_found
            exit 1
        fi

        echo SYNC_CONTAINER_ID=$container_id
        while IFS= read -r relpath; do
            [ -n "$relpath" ] || continue
            src="$REMOTE_DIR/$relpath"
            if [ ! -f "$src" ]; then
                echo ERROR=missing_source:$src
                exit 1
            fi
            echo SYNC_FILE_START=$relpath
            docker cp "$src" "$container_id:$APP_ROOT/$relpath"
            echo SYNC_FILE_DONE=$relpath
        done <<'EOF_SYNC_FILES'
        __SYNC_FILE_LIST__
        EOF_SYNC_FILES

        echo RESTART_PHASE=restart
        docker restart "$container_id"
        echo RESTART_LOGS_START
        docker logs --tail "$LOG_LINES" "$container_id" 2>&1 | sed -n '1,200p'
        echo RESTART_LOGS_END
        """
    )
    return (
        template
        .replace("__REMOTE_DIR__", shell_quote(remote_dir))
        .replace("__LOG_LINES__", str(int(log_lines)))
        .replace("__SYNC_FILE_LIST__", file_list)
    )


def build_remote_rebuild_command(remote_dir: str, log_lines: int) -> str:
    template = dedent(
        """\
        set -e
        REMOTE_DIR=__REMOTE_DIR__
        LOG_LINES=__LOG_LINES__
        COMPOSE_SERVICE=api_performances
        CONTAINER_NAME=lka_perf_api

        echo REBUILD_PHASE=prepare
        cd "$REMOTE_DIR"
        echo REBUILD_REMOTE_DIR=$(pwd)

        if docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD="docker compose"
        elif command -v docker-compose >/dev/null 2>&1; then
            COMPOSE_CMD="docker-compose"
        else
            echo ERROR=docker_compose_not_found
            exit 1
        fi

        echo REBUILD_COMPOSE_CMD=$COMPOSE_CMD
        echo REBUILD_PHASE=build
        $COMPOSE_CMD -f docker-compose.yml build "$COMPOSE_SERVICE"

        echo REBUILD_PHASE=up
        $COMPOSE_CMD -f docker-compose.yml up -d "$COMPOSE_SERVICE"

        echo REBUILD_PHASE=ps
        $COMPOSE_CMD -f docker-compose.yml ps "$COMPOSE_SERVICE" || true

        container_id="$(docker ps -aqf name=$CONTAINER_NAME | head -n 1)"
        echo REBUILD_CONTAINER_ID=$container_id
        if [ -n "$container_id" ]; then
            echo REBUILD_LOGS_START
            docker logs --tail "$LOG_LINES" "$container_id" 2>&1 | sed -n '1,200p'
            echo REBUILD_LOGS_END
        fi
        """
    )
    return (
        template
        .replace("__REMOTE_DIR__", shell_quote(remote_dir))
        .replace("__LOG_LINES__", str(int(log_lines)))
    )


def upload_relative_paths(client, remote_dir: str, relative_paths: list[str]):
    if not relative_paths:
        return

    sftp = client.open_sftp()
    try:
        for relative_path in relative_paths:
            local_path = (ROOT / relative_path).resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"Local file not found: {local_path}")

            remote_path = posixpath.join(remote_dir, relative_path.replace("\\", "/"))
            remote_parent = posixpath.dirname(remote_path)
            display_path = local_path.relative_to(ROOT).as_posix()

            run_remote_command(
                client,
                f"mkdir -p {shell_quote(remote_parent)}",
                timeout=30,
            )
            log(f"Uploading {display_path} -> {remote_path}")
            sftp.put(str(local_path), remote_path)
            log(f"Uploaded {display_path} ({local_path.stat().st_size} bytes)")
    finally:
        sftp.close()


def build_remote_probe_command(args) -> str:
    public_base_url = resolve_public_base_url(args)
    candidate_args = " ".join(
        shell_quote(path)
        for path in dict.fromkeys([args.remote_dir, *DEFAULT_REMOTE_CANDIDATES])
    )

    template = dedent(
        """\
        set +e
        set -u

        INPUT_REMOTE_DIR=__INPUT_REMOTE_DIR__
        OPT_ROOT=__OPT_ROOT__
        API_PORT=__API_PORT__
        SAMPLE_ID=__SAMPLE_ID__
        PUBLIC_BASE_URL=__PUBLIC_BASE_URL__
        HTTP_RETRIES=__HTTP_RETRIES__
        HTTP_DELAY=__HTTP_DELAY__
        HTTP_PYTHON="$(command -v python3 || command -v python || true)"

        find_remote_dir() {
            if [ -d "$INPUT_REMOTE_DIR" ]; then
                printf '%s\n' "$INPUT_REMOTE_DIR"
                return 0
            fi

            for candidate in __CANDIDATE_ARGS__; do
                if [ -d "$candidate" ]; then
                    printf '%s\n' "$candidate"
                    return 0
                fi
            done

            find "$OPT_ROOT" -maxdepth 2 -type d \\( -name '*perf*' -o -name '*commission*' -o -name '*lka*' \\) 2>/dev/null | while IFS= read -r dir; do
                if [ -f "$dir/api.py" ] || [ -f "$dir/docker-compose.yml" ] || [ -f "$dir/run_server.sh" ]; then
                    printf '%s\n' "$dir"
                fi
            done | head -n 1
        }

        probe_http() {
            label="$1"
            url="$2"
            attempt=1

            echo "${label}_URL=$url"

            if [ -z "$HTTP_PYTHON" ]; then
                echo "${label}_STATUS=SKIP"
                echo "${label}_BODY=python_not_found"
                return 1
            fi

            while [ "$attempt" -le "$HTTP_RETRIES" ]; do
                echo "${label}_TRY=$attempt"
                result="$($HTTP_PYTHON - "$url" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
request = urllib.request.Request(url, headers={"Accept": "application/json"})

try:
    with urllib.request.urlopen(request, timeout=8) as response:
        body = response.read(4000).decode("utf-8", errors="replace")
        print("STATUS=" + str(response.getcode()))
        print("BODY=" + body.replace("\\n", "\\\\n"))
except urllib.error.HTTPError as exc:
    body = exc.read(4000).decode("utf-8", errors="replace")
    print("STATUS=" + str(exc.code))
    print("BODY=" + body.replace("\\n", "\\\\n"))
except Exception as exc:
    print("STATUS=ERROR")
    print("BODY=" + repr(exc))
PY
                )"

                printf '%s\n' "$result" | sed "s/^/${label}_/"
                status="$(printf '%s\n' "$result" | sed -n 's/^STATUS=//p' | tail -n 1)"

                if [ -n "$status" ] && [ "$status" != "ERROR" ]; then
                    return 0
                fi

                attempt=$((attempt + 1))
                if [ "$attempt" -le "$HTTP_RETRIES" ]; then
                    sleep "$HTTP_DELAY"
                fi
            done

            return 1
        }

        echo HOSTNAME=$(hostname)
        echo NOW_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
        echo INPUT_REMOTE_DIR=$INPUT_REMOTE_DIR
        echo OPT_ROOT=$OPT_ROOT
        echo API_PORT=$API_PORT
        echo PUBLIC_BASE_URL=$PUBLIC_BASE_URL
        echo GIT_PATH=$(command -v git || true)
        echo PYTHON3_PATH=$(command -v python3 || true)
        echo DOCKER_PATH=$(command -v docker || true)
        echo SS_PATH=$(command -v ss || true)

        echo OPT_LIST_START
        ls -la "$OPT_ROOT" 2>/dev/null | sed -n '1,120p'
        echo OPT_LIST_END

        RESOLVED_REMOTE_DIR="$(find_remote_dir)"
        if [ -n "$RESOLVED_REMOTE_DIR" ] && [ -d "$RESOLVED_REMOTE_DIR" ]; then
            echo REMOTE_DIR_FOUND=yes
            echo RESOLVED_REMOTE_DIR=$RESOLVED_REMOTE_DIR
        else
            echo REMOTE_DIR_FOUND=no
            echo RESOLVED_REMOTE_DIR=
        fi

        PYTHON_BIN=
        if [ -n "$RESOLVED_REMOTE_DIR" ] && [ -d "$RESOLVED_REMOTE_DIR" ]; then
            echo APP_LIST_START
            ls -la "$RESOLVED_REMOTE_DIR" | sed -n '1,160p'
            echo APP_LIST_END

            if [ -d "$RESOLVED_REMOTE_DIR/.git" ]; then
                echo GIT_EXISTS=yes
                echo GIT_STATUS_START
                git -C "$RESOLVED_REMOTE_DIR" status --short --branch || true
                echo GIT_STATUS_END
                echo GIT_REMOTE_START
                git -C "$RESOLVED_REMOTE_DIR" remote -v | sed -E 's#(https?://)[^/@]+@#\\1#g' || true
                echo GIT_REMOTE_END
                echo GIT_LOG_START
                git -C "$RESOLVED_REMOTE_DIR" log --oneline -n 5 || true
                echo GIT_LOG_END
            else
                echo GIT_EXISTS=no
            fi

            if [ -x "$RESOLVED_REMOTE_DIR/venv/bin/python" ]; then
                PYTHON_BIN="$RESOLVED_REMOTE_DIR/venv/bin/python"
                echo VENV_EXISTS=yes
                echo VENV_KIND=venv
            elif [ -x "$RESOLVED_REMOTE_DIR/.venv/bin/python" ]; then
                PYTHON_BIN="$RESOLVED_REMOTE_DIR/.venv/bin/python"
                echo VENV_EXISTS=yes
                echo VENV_KIND=.venv
            else
                echo VENV_EXISTS=no
                echo VENV_KIND=
            fi
            echo VENV_PYTHON=$PYTHON_BIN

            if [ -f "$RESOLVED_REMOTE_DIR/docker-compose.yml" ]; then
                echo DOCKER_COMPOSE_START
                sed -n '1,120p' "$RESOLVED_REMOTE_DIR/docker-compose.yml"
                echo DOCKER_COMPOSE_END
            fi

            if [ -f "$RESOLVED_REMOTE_DIR/Dockerfile.api" ]; then
                echo DOCKERFILE_API_START
                sed -n '1,120p' "$RESOLVED_REMOTE_DIR/Dockerfile.api"
                echo DOCKERFILE_API_END
            fi

            if [ -f "$RESOLVED_REMOTE_DIR/.env" ]; then
                echo ENV_SUMMARY_START
                sed -n '/^PERF_MYSQL_HOST/p;/^PERF_MYSQL_PORT/p;/^PERF_MYSQL_DATABASE/p' "$RESOLVED_REMOTE_DIR/.env"
                echo ENV_SUMMARY_END
            fi

            if [ -d "$RESOLVED_REMOTE_DIR/logs" ]; then
                latest_log="$(ls -1t "$RESOLVED_REMOTE_DIR"/logs/*.log 2>/dev/null | head -n 1)"
                echo LATEST_LOG=$latest_log
                if [ -n "$latest_log" ]; then
                    echo APP_LOG_TAIL_START
                    tail -n 80 "$latest_log"
                    echo APP_LOG_TAIL_END
                fi
            fi
        fi

        echo PROCESS_CHECK_START
        ps -ef | grep -E 'uvicorn|api:app|lka_perf_api|docker' | grep -v grep | sed -n '1,160p'
        echo PROCESS_CHECK_END

        echo PORT_CHECK_START
        if command -v ss >/dev/null 2>&1; then
            ss -ltnp 2>/dev/null | grep -E ":$API_PORT\\b" | sed -n '1,80p'
        elif command -v netstat >/dev/null 2>&1; then
            netstat -ltnp 2>/dev/null | grep -E ":$API_PORT\\b" | sed -n '1,80p'
        fi
        echo PORT_CHECK_END

        echo SYSTEMD_CHECK_START
        if command -v systemctl >/dev/null 2>&1; then
            systemctl list-units --type=service --all 2>/dev/null | grep -iE 'perf|api|uvicorn' | sed -n '1,80p'
        fi
        echo SYSTEMD_CHECK_END

        echo DOCKER_CHECK_START
        if command -v docker >/dev/null 2>&1; then
            echo DOCKER_AVAILABLE=yes
            docker ps -a --filter name=lka_perf_api 2>&1 | sed -n '1,80p'
            docker_id="$(docker ps -a --filter name=lka_perf_api --quiet 2>/dev/null | head -n 1)"
            echo DOCKER_CONTAINER_ID=$docker_id
            if [ -n "$docker_id" ]; then
                echo DOCKER_LOGS_START
                docker logs --tail 120 "$docker_id" 2>&1 | sed -n '1,160p'
                echo DOCKER_LOGS_END
            fi
        else
            echo DOCKER_AVAILABLE=no
        fi
        echo DOCKER_CHECK_END

        LOCAL_BASE_URL="http://127.0.0.1:$API_PORT"
        probe_http LOCAL_ROOT "$LOCAL_BASE_URL/"
        probe_http LOCAL_DOCS "$LOCAL_BASE_URL/docs"
        probe_http LOCAL_PERFORMANCE "$LOCAL_BASE_URL/api/performances/$SAMPLE_ID"
        probe_http PUBLIC_ROOT "$PUBLIC_BASE_URL/"
        probe_http PUBLIC_DOCS "$PUBLIC_BASE_URL/docs"
        probe_http PUBLIC_PERFORMANCE "$PUBLIC_BASE_URL/api/performances/$SAMPLE_ID"

        if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ] && [ -n "$RESOLVED_REMOTE_DIR" ] && [ -d "$RESOLVED_REMOTE_DIR" ]; then
            echo PYTHON_DIAG_START
            export API_PROBE_ID="$SAMPLE_ID"
            cd "$RESOLVED_REMOTE_DIR" || exit 1
            "$PYTHON_BIN" - <<'PY'
import importlib.util
import os
import traceback


def report(name, value):
    print(name + "=" + str(value))


for module_name in ("fastapi", "uvicorn", "sqlalchemy", "pymysql", "dotenv", "paramiko"):
    report("MODULE_" + module_name.upper(), "yes" if importlib.util.find_spec(module_name) else "no")

try:
    import api
    report("API_IMPORT", "ok")
    report("API_ENGINE_NONE", "yes" if getattr(api, "engine", None) is None else "no")
except Exception as exc:
    report("API_IMPORT", "error")
    report("API_IMPORT_ERROR", repr(exc))
    traceback.print_exc()

try:
    from sqlalchemy import text
    from connections.connect import make_engine

    engine = make_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        report("DB_SELECT_1", "ok")
        try:
            row = conn.execute(
                text(
                    "SELECT user_name, agent_name FROM lka_client_mtn.lka_usernames "
                    "WHERE id_pulse = :id_pulse LIMIT 1"
                ),
                {"id_pulse": os.environ.get("API_PROBE_ID", "TEST123")},
            ).fetchone()
            report("LKA_USER_LOOKUP", "ok")
            report("LKA_USER_FOUND", "yes" if row else "no")
        except Exception as query_exc:
            report("LKA_USER_LOOKUP", "error")
            report("LKA_USER_LOOKUP_ERROR", repr(query_exc))
except Exception as exc:
    report("DB_SELECT_1", "error")
    report("DB_SELECT_1_ERROR", repr(exc))
    traceback.print_exc()
PY
            echo PYTHON_DIAG_END
        fi
        """
    )

    return (
        template
        .replace("__INPUT_REMOTE_DIR__", shell_quote(args.remote_dir))
        .replace("__OPT_ROOT__", shell_quote(args.opt_root))
        .replace("__API_PORT__", str(int(args.api_port)))
        .replace("__SAMPLE_ID__", shell_quote(args.sample_id))
        .replace("__PUBLIC_BASE_URL__", shell_quote(public_base_url))
        .replace("__HTTP_RETRIES__", str(int(args.http_retries)))
        .replace("__HTTP_DELAY__", str(int(args.http_delay)))
        .replace("__CANDIDATE_ARGS__", candidate_args)
    )


def main():
    if PARAMIKO_IMPORT_ERROR is not None:
        print(f"paramiko is required to run this probe: {PARAMIKO_IMPORT_ERROR}", file=sys.stderr)
        return 2

    args = parse_args()
    if not args.ssh_pass:
        args.ssh_pass = os.environ.get("LKA_SSH_PASS")
    if not args.ssh_pass:
        args.ssh_pass = getpass.getpass("SSH password: ")

    upload_paths = []
    if args.upload_api_files:
        upload_paths.extend(DEFAULT_API_SYNC_FILES)
    upload_paths.extend(args.upload_path)
    upload_paths = list(dict.fromkeys(upload_paths))

    client = None
    try:
        client = connect_with_retry(args)
        if upload_paths or args.rebuild_api:
            log("Resolving remote application directory.")
            args.remote_dir = resolve_remote_dir_on_server(client, args)
            log(f"Remote application directory: {args.remote_dir}")

        if upload_paths:
            log("Uploading local API files to the VPS.")
            upload_relative_paths(client, args.remote_dir, upload_paths)

        if args.rebuild_api:
            log("Rebuilding and restarting the remote API container.")
            rebuild_exit, _, _ = run_remote_command(
                client,
                build_remote_rebuild_command(args.remote_dir, args.rebuild_log_lines),
                timeout=args.command_timeout,
                stream=True,
            )
            if rebuild_exit != 0:
                raise RuntimeError(f"Remote API rebuild failed with exit code {rebuild_exit}.")
            log("Remote API rebuild completed.")

        if args.sync_running_container:
            if not upload_paths:
                raise ValueError("--sync-running-container requires uploaded files. Use --upload-path or --upload-api-files.")
            log("Syncing uploaded files into the running API container and restarting it.")
            sync_exit, _, _ = run_remote_command(
                client,
                build_remote_container_sync_command(args.remote_dir, upload_paths, args.rebuild_log_lines),
                timeout=args.command_timeout,
                stream=True,
            )
            if sync_exit != 0:
                raise RuntimeError(f"Remote container sync failed with exit code {sync_exit}.")
            log("Remote API container sync completed.")

        if args.skip_diagnosis:
            return 0

        log("Running remote API diagnosis.")
        command = build_remote_probe_command(args)
        exit_status, output, errors = run_remote_command(
            client,
            command,
            timeout=args.command_timeout,
        )
        print(output)
        if errors.strip():
            print("STDERR_START")
            print(errors)
            print("STDERR_END")
        return exit_status
    except Exception as exc:
        log(f"API diagnosis failed: {exc.__class__.__name__}: {exc}")
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    sys.exit(main())