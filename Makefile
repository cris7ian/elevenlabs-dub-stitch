# dubstitch — common tasks. Recipes use the inline ";" form so no tabs are needed.
PYTHON ?= python3
URL ?= https://youtu.be/Bs6ev0utXbs
DURATION ?= 5
TARGETS ?= en,de,ja,fr,ar,ko,it
LAYOUT ?= band

help: ; @echo "make test | fonts | demo | clip | submit | fetch | render | clean"
test: ; $(PYTHON) -m pytest
fonts: ; $(PYTHON) -m dubstitch fonts
demo: ; $(PYTHON) -m dubstitch all "$(URL)" --duration $(DURATION) --targets $(TARGETS) --layout $(LAYOUT)
clip: ; $(PYTHON) -m dubstitch clip "$(URL)" --duration $(DURATION)
submit: ; $(PYTHON) -m dubstitch submit --targets $(TARGETS)
fetch: ; $(PYTHON) -m dubstitch fetch
render: ; $(PYTHON) -m dubstitch render --layout $(LAYOUT)
clean: ; @rm -rf work/renders work/frames .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
