PKG_NAME:="rediscron"
PKG_VERSION:=$(shell uv tool run hatch version)

SEGMENT ?= patch

# Test the code then bump the package semver version, update uv lock file,
# commit the update, tag the poject with the new version.
# By default, update the patch version. This can be modified by using the
# SEGMENT variable.
# eg. $ make bump SEGMENT=minor
# Valid segment values are defined by hatch:
# https://hatch.pypa.io/1.16/version/#supported-segments
.PHONY: bump
bump: test
	git checkout main
	uv tool run hatch version $(SEGMENT)
	git add rediscron/__meta__.py
	uv lock
	git add uv.lock
	pkg_ver=$$(uv tool run hatch version); \
	git commit -m "release: bump to $${pkg_ver}"; \
	git tag -a v$${pkg_ver} -m "release: bump to $${pkg_ver}"

.PHONY: buildclean
buildclean:
	rm -rf *egg-info build dist

# Build the package using uv and defined packaging backend
.PHONY: build
build: buildclean tox
	uv build

# Build and push the package to the defined package index
.PHONY: publish
publish: build
	uv publish

# Push code & tags to the upstream repository
.PHONY: push
push:
	git push upstream --tags

# Bump, Publish and Push the project
.PHONY: release
release: bump publish push

.PHONY: unittest
unittest:
	uv run python -m unittest discover

.PHONY: tox
tox:
	uv run tox

.PHONY: test
test: tox

.PHONY: fulltest
fulltest: tox unittest

.PHONY: docs
docs:
	make -C docs/ -f Makefile html SPHINXBUILD='uv run sphinx-build'
