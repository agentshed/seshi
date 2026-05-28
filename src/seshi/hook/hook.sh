#!/usr/bin/env bash
set -euo pipefail

SESHI_DIR="$HOME/.seshi"
QUEUE="$SESHI_DIR/queue.jsonl"

EVENT="$1"
INPUT=$(cat) || exit 0

SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null) || exit 0
[ -z "$SESSION_ID" ] && exit 0

CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null) || CWD=""

mkdir -p "$SESHI_DIR" 2>/dev/null || exit 0

json_escape() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))" 2>/dev/null || echo "\"$(echo "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')\""
}

TS=$(date +%s) || TS=0

if [ "$EVENT" = "start" ]; then
    if [ "$(uname)" = "Linux" ] && [ -f "/proc/$PPID/cmdline" ]; then
        ARGV=$(tr '\0' ' ' < "/proc/$PPID/cmdline" 2>/dev/null | sed 's/ *$//') || ARGV=""
    else
        ARGV=$(ps -o args= -p "$PPID" 2>/dev/null) || ARGV=""
    fi
    ARGV_JSON=$(echo "$ARGV" | json_escape) || ARGV_JSON='""'

    GIT_BRANCH=""
    GIT_SHA=""
    if [ -n "$CWD" ] && [ -d "$CWD" ]; then
        GIT_BRANCH=$(cd "$CWD" && git rev-parse --abbrev-ref HEAD 2>/dev/null) || GIT_BRANCH=""
        GIT_SHA=$(cd "$CWD" && git rev-parse HEAD 2>/dev/null) || GIT_SHA=""
    fi

    ENV_JSON="{"
    [ -n "${ANTHROPIC_MODEL:-}" ] && ENV_JSON="$ENV_JSON\"ANTHROPIC_MODEL\":\"$ANTHROPIC_MODEL\","
    [ -n "${ANTHROPIC_BASE_URL:-}" ] && ENV_JSON="$ENV_JSON\"ANTHROPIC_BASE_URL\":\"$ANTHROPIC_BASE_URL\","
    [ -n "${CLAUDE_CODE_USE_BEDROCK:-}" ] && ENV_JSON="$ENV_JSON\"CLAUDE_CODE_USE_BEDROCK\":\"$CLAUDE_CODE_USE_BEDROCK\","
    [ -n "${CLAUDE_CODE_USE_VERTEX:-}" ] && ENV_JSON="$ENV_JSON\"CLAUDE_CODE_USE_VERTEX\":\"$CLAUDE_CODE_USE_VERTEX\","
    [ -n "${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-}" ] && ENV_JSON="$ENV_JSON\"CLAUDE_CODE_MAX_OUTPUT_TOKENS\":\"$CLAUDE_CODE_MAX_OUTPUT_TOKENS\","
    ENV_JSON=$(echo "$ENV_JSON" | sed 's/,$//')
    ENV_JSON="$ENV_JSON}"

    ORIGIN_HOST=$(hostname -s 2>/dev/null) || ORIGIN_HOST=""

    printf '{"event":"start","ts":%s,"session_id":"%s","cwd":"%s","argv":%s,"env":%s,"git_branch":"%s","git_sha":"%s","origin_host":"%s"}\n' \
        "$TS" "$SESSION_ID" "$CWD" "$ARGV_JSON" "$ENV_JSON" "$GIT_BRANCH" "$GIT_SHA" "$ORIGIN_HOST" \
        >> "$QUEUE" 2>/dev/null || exit 0

elif [ "$EVENT" = "stop" ]; then
    TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null) || TRANSCRIPT_PATH=""

    MSG_COUNT=0
    TOKEN_COUNT=0
    FIRST_PROMPT=""

    if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
        MSG_COUNT=$(wc -l < "$TRANSCRIPT_PATH" 2>/dev/null | tr -d ' ') || MSG_COUNT=0

        TOKEN_COUNT=$(python3 -c "
import json, sys
total = 0
for line in open('$TRANSCRIPT_PATH'):
    try:
        obj = json.loads(line)
        usage = obj.get('message', {}).get('usage', {})
        total += usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
    except: pass
print(total)
" 2>/dev/null) || TOKEN_COUNT=0

        FIRST_PROMPT=$(python3 -c "
import json, re, sys
_SYS_RE = re.compile(r'<(local-command-caveat|system-reminder|command-name|command-message|command-args|local-command-stdout|task-notification)(?:\s[^>]*)?>.*?</\1>', re.DOTALL)
for line in open('$TRANSCRIPT_PATH'):
    try:
        obj = json.loads(line)
        msg = obj.get('message', {})
        if msg.get('role') == 'user' and not obj.get('isMeta'):
            content = msg.get('content', '')
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        content = block.get('text', '')
                        break
                else:
                    content = ''
            content = _SYS_RE.sub('', str(content)).strip()
            if content:
                print(content[:200])
                break
    except: pass
" 2>/dev/null) || FIRST_PROMPT=""
        FIRST_PROMPT_JSON=$(echo "$FIRST_PROMPT" | json_escape) || FIRST_PROMPT_JSON='""'
    else
        FIRST_PROMPT_JSON='""'
    fi

    printf '{"event":"stop","ts":%s,"session_id":"%s","message_count":%s,"token_count":%s,"first_prompt":%s}\n' \
        "$TS" "$SESSION_ID" "$MSG_COUNT" "$TOKEN_COUNT" "$FIRST_PROMPT_JSON" \
        >> "$QUEUE" 2>/dev/null || exit 0
fi

exit 0
