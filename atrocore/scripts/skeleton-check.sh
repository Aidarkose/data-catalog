#!/bin/bash

VARIANTS=("pim-no-demo" "atrocore")
STABILITIES=("stable" "rc" "beta")

check_argument() {
    local arg="$1"
    shift
    local options=("$@")

    for valid in "${options[@]}"; do
        if [[ "$valid" == "$arg" ]]; then
            return 0
        fi
    done
    return 1
}

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <variant> <stability>"
    echo "Supported variants: ${VARIANTS[*]}"
    echo "Supported stabilities: ${STABILITIES[*]}"
    exit 1
fi

if ! check_argument "$1" "${VARIANTS[@]}"; then
    echo "Invalid variant: $1"
    echo "Supported variants: ${VARIANTS[*]}"
    exit 1
fi

if ! check_argument "$2" "${STABILITIES[@]}"; then
    echo "Invalid stability: $2"
    echo "Supported stabilities: ${STABILITIES[*]}"
    exit 1
fi
