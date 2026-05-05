#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
ENV_TEMPLATE="$BACKEND_DIR/.env.example"

if [[ ! -f "$ENV_TEMPLATE" ]]; then
  echo "Missing template: $ENV_TEMPLATE"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  echo "Created $ENV_FILE from template."
fi

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -v k="$key" -v v="$value" '
    BEGIN { updated = 0 }
    $0 ~ "^" k "=" {
      print k "=" v
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print k "=" v
      }
    }
  ' "$ENV_FILE" > "$tmp_file"
  mv "$tmp_file" "$ENV_FILE"
}

ask_value() {
  local prompt="$1"
  local default_value="$2"
  local is_secret="${3:-false}"
  local value=""

  if [[ "$is_secret" == "true" ]]; then
    read -r -s -p "$prompt [$default_value]: " value
    echo
  else
    read -r -p "$prompt [$default_value]: " value
  fi

  if [[ -z "$value" ]]; then
    value="$default_value"
  fi
  echo "$value"
}

echo "Configuring backend environment: $ENV_FILE"
echo
echo "Choose embedding provider:"
echo "1) dashscope_multimodal (recommended for qwen3-vl-embedding / tongyi-embedding-vision-*)"
echo "2) openai_compatible"
read -r -p "Select [1]: " provider_choice
provider_choice="${provider_choice:-1}"

embedding_provider="dashscope_multimodal"
embedding_model="tongyi-embedding-vision-flash-2026-03-06"
embedding_base_url=""
embedding_dim_default="768"

if [[ "$provider_choice" == "2" ]]; then
  embedding_provider="openai_compatible"
  embedding_model="text-embedding-v4"
  embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
  embedding_dim_default="1536"
fi

embedding_provider="$(ask_value "EMBEDDING_PROVIDER" "$embedding_provider")"
embedding_model="$(ask_value "EMBEDDING_MODEL" "$embedding_model")"
embedding_batch_size="$(ask_value "EMBEDDING_BATCH_SIZE" "5")"
embedding_dim="$(ask_value "EMBEDDING_DIM" "$embedding_dim_default")"
embedding_api_key="$(ask_value "EMBEDDING_API_KEY" "" "true")"

glm_base_url="$(ask_value "GLM5_ROUTER_BASE_URL" "https://dashscope.aliyuncs.com/compatible-mode/v1")"
glm_model="$(ask_value "GLM5_ROUTER_MODEL" "glm-5")"
glm_key="$(ask_value "GLM5_ROUTER_API_KEY" "" "true")"

qwen_base_url="$(ask_value "QWEN_ANSWER_BASE_URL" "https://dashscope.aliyuncs.com/compatible-mode/v1")"
qwen_model="$(ask_value "QWEN_ANSWER_MODEL" "qwen3.5-plus")"
qwen_key="$(ask_value "QWEN_ANSWER_API_KEY" "" "true")"

tavily_key="$(ask_value "TAVILY_API_KEY (optional)" "" "true")"
milvus_mode="$(ask_value "MILVUS_MODE (remote/lite/memory)" "remote")"
milvus_uri_default="http://127.0.0.1:19530"
if [[ "$milvus_mode" == "lite" ]]; then
  milvus_uri_default="./data/milvus_lite.db"
fi
milvus_uri="$(ask_value "MILVUS_URI" "$milvus_uri_default")"
hachi_mock_mode="$(ask_value "HACHI_MOCK_MODE" "false")"

set_env_value "EMBEDDING_PROVIDER" "$embedding_provider"
set_env_value "EMBEDDING_MODEL" "$embedding_model"
set_env_value "EMBEDDING_BATCH_SIZE" "$embedding_batch_size"
set_env_value "EMBEDDING_DIM" "$embedding_dim"
set_env_value "EMBEDDING_API_KEY" "$embedding_api_key"

# Keep base URL in sync only for openai_compatible. For multimodal it's optional.
if [[ "$embedding_provider" == "openai_compatible" ]]; then
  embedding_base_url="$(ask_value "EMBEDDING_BASE_URL" "$embedding_base_url")"
  set_env_value "EMBEDDING_BASE_URL" "$embedding_base_url"
fi

set_env_value "GLM5_ROUTER_BASE_URL" "$glm_base_url"
set_env_value "GLM5_ROUTER_MODEL" "$glm_model"
set_env_value "GLM5_ROUTER_API_KEY" "$glm_key"

set_env_value "QWEN_ANSWER_BASE_URL" "$qwen_base_url"
set_env_value "QWEN_ANSWER_MODEL" "$qwen_model"
set_env_value "QWEN_ANSWER_API_KEY" "$qwen_key"

set_env_value "TAVILY_API_KEY" "$tavily_key"
set_env_value "MILVUS_MODE" "$milvus_mode"
set_env_value "MILVUS_URI" "$milvus_uri"
set_env_value "HACHI_MOCK_MODE" "$hachi_mock_mode"

echo
echo "Done. Environment file updated:"
echo "  $ENV_FILE"
