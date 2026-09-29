#!/usr/bin/env bash
# Generate the Python gRPC stubs from proto/ (written next to the .proto files).
#
# The protos import each other by BARE name ("import assessment_request.proto"),
# so each proto dir is its own -I root -- and the generated stubs import each
# other by bare module name too, which is why the clients put every proto dir on
# sys.path.
#
#   pip install -r requirements.txt && ./gen_stubs.sh
#   PYTHON=/path/to/venv/bin/python3 ./gen_stubs.sh   # to use a specific python
set -euo pipefail
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}

"$PYTHON" -c 'import grpc_tools' 2>/dev/null || {
  echo "grpcio-tools not installed for $PYTHON: pip install -r requirements.txt" >&2
  exit 1; }

# 2>/dev/null: protoc warns about unused imports in the vendored protos; harmless.
"$PYTHON" -m grpc_tools.protoc -Iproto -Iproto/assessment -Iproto/common \
  --python_out=proto --grpc_python_out=proto \
  proto/services.proto proto/recognition_response.proto \
  proto/olign_service.proto 2>/dev/null
"$PYTHON" -m grpc_tools.protoc -Iproto/assessment -Iproto/common -Iproto \
  --python_out=proto/assessment proto/assessment/*.proto 2>/dev/null
"$PYTHON" -m grpc_tools.protoc -Iproto/common \
  --python_out=proto/common proto/common/*.proto 2>/dev/null

echo "stubs generated:"
find proto -name '*_pb2*.py' | sort | sed 's/^/  /'
