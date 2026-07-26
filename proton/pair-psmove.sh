#!/bin/sh

result_file=$1
shift

"$@"
pair_result=$?

umask 000
printf '%s\n' "$pair_result" > "$result_file"
