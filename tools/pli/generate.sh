#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION=4.13.2
JAR="lib/antlr-${VERSION}-complete.jar"
URL="https://www.antlr.org/download/antlr-${VERSION}-complete.jar"

mkdir -p lib generated
if [ ! -f "$JAR" ]; then
  curl -fsSL "$URL" -o "$JAR"
fi
java -jar "$JAR" -Dlanguage=Python3 -o generated -visitor -no-listener pl1.g4
