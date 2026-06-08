#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
BFF_URL="${BFF_URL:-}"
RUN_ID="${RUN_ID:-$(date +%s)-$$-${RANDOM:-0}}"

json_value() {
  local expression="$1"
  python -c 'import json, sys
payload = json.load(sys.stdin)
value = payload
for part in sys.argv[1].split("."):
    if not part:
        continue
    value = value[part]
print(value)' "$expression"
}

require_contains() {
  local haystack="$1"
  local needle="$2"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "expected output to contain: $needle" >&2
    echo "$haystack" >&2
    exit 1
  fi
}

require_http_status() {
  local expected="$1"
  local url="$2"
  local method="${3:-GET}"
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url")"
  if [[ "$status" != "$expected" ]]; then
    echo "expected $method $url to return $expected, got $status" >&2
    exit 1
  fi
}

post_json() {
  local url="$1"
  local body="$2"
  curl -fsS -X POST "$url" -H "Content-Type: application/json" --data "$body"
}

message_send_payload() {
  local request_id="$1"
  local message_id="$2"
  local text="$3"
  local execution_mode="$4"
  python - "$request_id" "$message_id" "$text" "$execution_mode" <<'PY'
import json
import sys

request_id, message_id, text, execution_mode = sys.argv[1:5]
print(json.dumps({
    "jsonrpc": "2.0",
    "id": request_id,
    "method": "message/send",
    "params": {
        "message": {
            "kind": "message",
            "role": "user",
            "messageId": message_id,
            "parts": [{"kind": "text", "text": text}],
        },
        "metadata": {"executionMode": execution_mode},
    },
}, separators=(",", ":")))
PY
}

echo "A2A smoke: backend=$BASE_URL"
echo "Checking path-style compatibility routes"

message_response="$(
  post_json "$BASE_URL/message:send" "$(
    message_send_payload "smoke-message-$RUN_ID" "msg-smoke-message-$RUN_ID" "hello smoke" "message"
  )"
)"
message_kind="$(printf '%s' "$message_response" | json_value "result.kind")"
if [[ "$message_kind" != "message" ]]; then
  echo "expected message result, got: $message_kind" >&2
  exit 1
fi

task_response="$(
  post_json "$BASE_URL/message:send" "$(
    message_send_payload "smoke-task-$RUN_ID" "msg-smoke-task-$RUN_ID" "run smoke task" "task"
  )"
)"
task_id="$(printf '%s' "$task_response" | json_value "result.id")"
task_state="$(printf '%s' "$task_response" | json_value "result.status.state")"
if [[ -z "$task_id" || "$task_state" != "completed" ]]; then
  echo "expected completed task, got id=$task_id state=$task_state" >&2
  exit 1
fi

get_response="$(curl -fsS "$BASE_URL/tasks/$task_id")"
get_task_id="$(printf '%s' "$get_response" | json_value "result.id")"
if [[ "$get_task_id" != "$task_id" ]]; then
  echo "task get mismatch: expected=$task_id got=$get_task_id" >&2
  exit 1
fi

echo "Checking canonical /rpc routes"

rpc_message_response="$(
  post_json "$BASE_URL/rpc" "$(
    message_send_payload "rpc-smoke-message-$RUN_ID" "msg-rpc-smoke-message-$RUN_ID" "hello rpc smoke" "message" \
      | python -c 'import json, sys
payload = json.load(sys.stdin)
payload["method"] = "SendMessage"
print(json.dumps(payload, separators=(",", ":")))'
  )"
)"
rpc_message_kind="$(printf '%s' "$rpc_message_response" | json_value "result.kind")"
if [[ "$rpc_message_kind" != "message" ]]; then
  echo "expected rpc message result, got: $rpc_message_kind" >&2
  exit 1
fi

rpc_get_response="$(
  post_json "$BASE_URL/rpc" "{\"jsonrpc\":\"2.0\",\"id\":\"rpc-get-smoke-$RUN_ID\",\"method\":\"GetTask\",\"params\":{\"id\":\"$task_id\"}}"
)"
rpc_get_task_id="$(printf '%s' "$rpc_get_response" | json_value "result.id")"
if [[ "$rpc_get_task_id" != "$task_id" ]]; then
  echo "rpc task get mismatch: expected=$task_id got=$rpc_get_task_id" >&2
  exit 1
fi

rpc_stream_response="$(
  post_json "$BASE_URL/rpc" "$(
    message_send_payload "rpc-stream-smoke-$RUN_ID" "msg-rpc-stream-smoke-$RUN_ID" "run rpc stream smoke task" "task" \
      | python -c 'import json, sys
payload = json.load(sys.stdin)
payload["method"] = "SendStreamingMessage"
print(json.dumps(payload, separators=(",", ":")))'
  )"
)"
require_contains "$rpc_stream_response" "event: task"
require_contains "$rpc_stream_response" "event: artifact-update"
require_contains "$rpc_stream_response" "event: status-update"
require_contains "$rpc_stream_response" "\"id\": \"rpc-stream-smoke-$RUN_ID\""

rpc_subscribe_response="$(
  post_json "$BASE_URL/rpc" "{\"jsonrpc\":\"2.0\",\"id\":\"rpc-subscribe-smoke-$RUN_ID\",\"method\":\"SubscribeToTask\",\"params\":{\"id\":\"$task_id\",\"afterEventId\":0}}"
)"
require_contains "$rpc_subscribe_response" "event: artifact-update"
require_contains "$rpc_subscribe_response" "event: status-update"
require_contains "$rpc_subscribe_response" "\"id\": \"rpc-subscribe-smoke-$RUN_ID\""

subscribe_response="$(curl -fsS -X POST "$BASE_URL/tasks/${task_id}:subscribe")"
require_contains "$subscribe_response" "event: artifact-update"
require_contains "$subscribe_response" "event: status-update"
require_contains "$subscribe_response" '"state": "completed"'

cancel_error="$(
  curl -sS -X POST "$BASE_URL/tasks/${task_id}:cancel" \
    -H "Content-Type: application/json" \
    --data "{\"jsonrpc\":\"2.0\",\"id\":\"cancel-smoke-$RUN_ID\",\"method\":\"tasks/cancel\",\"params\":{\"id\":\"$task_id\",\"reason\":\"too late\"}}"
)"
require_contains "$cancel_error" "\"id\":\"cancel-smoke-$RUN_ID\""
require_contains "$cancel_error" '"localCode":"invalid_session_state"'
require_contains "$cancel_error" '"errorInfo"'

rpc_cancel_error="$(
  curl -sS -X POST "$BASE_URL/rpc" \
    -H "Content-Type: application/json" \
    --data "{\"jsonrpc\":\"2.0\",\"id\":\"rpc-cancel-smoke-$RUN_ID\",\"method\":\"CancelTask\",\"params\":{\"id\":\"$task_id\",\"reason\":\"too late\"}}"
)"
require_contains "$rpc_cancel_error" "\"id\":\"rpc-cancel-smoke-$RUN_ID\""
require_contains "$rpc_cancel_error" '"localCode":"invalid_session_state"'
require_contains "$rpc_cancel_error" '"errorInfo"'

echo "A2A backend smoke passed: task=$task_id"

require_http_status 404 "$BASE_URL/api/sessions"
require_http_status 404 "$BASE_URL/api/tasks/$task_id"
require_http_status 404 "$BASE_URL/api/tasks/$task_id/events"

if [[ -n "$BFF_URL" ]]; then
  echo "A2A BFF smoke: bff=$BFF_URL"

  bff_error="$(curl -sS "$BFF_URL/api/bff/agent/a2a/tasks/missing-task")"
  require_contains "$bff_error" '"message":"task not found"'
  require_contains "$bff_error" '"code":"task_not_found"'

  bff_message="$(
    post_json "$BFF_URL/api/bff/agent/a2a/message" '{
      "text": "hello bff message smoke",
      "executionMode": "message"
    }'
  )"
  bff_message_kind="$(printf '%s' "$bff_message" | json_value "kind")"
  if [[ "$bff_message_kind" != "message" ]]; then
    echo "expected BFF message result, got: $bff_message_kind" >&2
    exit 1
  fi

  bff_stream="$(
    post_json "$BFF_URL/api/bff/agent/a2a/message-stream" '{
      "text": "run bff smoke task",
      "executionMode": "task"
    }'
  )"
  require_contains "$bff_stream" "event: task"
  require_contains "$bff_stream" "event: artifact-update"
  require_contains "$bff_stream" "Dev mock task completed: run bff smoke task"

  bff_task="$(
    post_json "$BFF_URL/api/bff/agent/a2a/message" '{
      "text": "run bff cancel smoke task",
      "executionMode": "task"
    }'
  )"
  bff_task_id="$(printf '%s' "$bff_task" | json_value "task.id")"
  bff_task_snapshot="$(curl -fsS "$BFF_URL/api/bff/agent/a2a/tasks/$bff_task_id")"
  bff_task_snapshot_id="$(printf '%s' "$bff_task_snapshot" | json_value "id")"
  if [[ "$bff_task_snapshot_id" != "$bff_task_id" ]]; then
    echo "BFF task snapshot mismatch: expected=$bff_task_id got=$bff_task_snapshot_id" >&2
    exit 1
  fi
  bff_events="$(curl -fsS "$BFF_URL/api/bff/agent/a2a/tasks/$bff_task_id/events")"
  require_contains "$bff_events" "event: artifact-update"
  require_contains "$bff_events" "event: status-update"
  bff_cancel_error="$(
    curl -sS -X POST "$BFF_URL/api/bff/agent/a2a/tasks/$bff_task_id/cancel" \
      -H "Content-Type: application/json" \
      --data '{"reason":"too late"}'
  )"
  require_contains "$bff_cancel_error" '"status":409'
  require_contains "$bff_cancel_error" '"code":"invalid_session_state"'

  require_http_status 404 "$BFF_URL/api/bff/agent/sessions"
  require_http_status 404 "$BFF_URL/api/bff/agent/tasks/$bff_task_id"

  echo "A2A BFF smoke passed"
fi
