.DEFAULT_GOAL := run
IMAGE ?= formrehearsal-track2a-source-candidate:local
export IMAGE OUTPUT_ROOT OUTPUT_NAME PDF PREPARED INDEX IMPORTED EXPECTED_PREPARE EXPECTED_IMPORT CHUNK_CHARS
.PHONY: run build prepare import review comparison-demo test help
build:
	docker build --platform linux/amd64 --file ../Dockerfile --tag "$(IMAGE)" ..
run: build
	sh src/run-container.sh demo
prepare import review comparison-demo test: build
	sh src/run-container.sh $@
help:
	@printf '%s\n' 'make run: owned synthetic PDF -> authored originals -> strict import -> source-first review (zero model calls)' 'make prepare PDF=/absolute/source.pdf OUTPUT_ROOT=/absolute/output-parent OUTPUT_NAME=prepared' 'make import PREPARED=/absolute/prepared INDEX=/absolute/captures/index.json EXPECTED_PREPARE=<pin> OUTPUT_ROOT=/absolute/output-parent OUTPUT_NAME=imported' 'make review PREPARED=/absolute/prepared IMPORTED=/absolute/imported EXPECTED_IMPORT=<pin> OUTPUT_ROOT=/absolute/output-parent OUTPUT_NAME=review' 'make comparison-demo: owned two-packet question worksheet' 'make test: offline converter and worksheet engineering tests in Docker'
