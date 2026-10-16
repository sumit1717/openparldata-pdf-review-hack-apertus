.DEFAULT_GOAL := run
.PHONY: run build prepare import review comparison-demo test help
run build prepare import review comparison-demo test help:
	$(MAKE) -C track_2a $@
