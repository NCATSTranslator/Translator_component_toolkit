# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SPHINXAPIDOC  ?= sphinx-apidoc
SOURCEDIR     = source
BUILDDIR      = build
PKGDIR        = ../TCT
APIDIR        = $(SOURCEDIR)/api

# Modules with a hand-maintained page in source/ are excluded here, so apidoc
# only generates stubs for modules that would otherwise go undocumented.
APIDOC_EXCLUDE = \
	$(PKGDIR)/TCT.py \
	$(PKGDIR)/name_resolver.py \
	$(PKGDIR)/node_normalizer.py \
	$(PKGDIR)/node_annotator.py \
	$(PKGDIR)/translator_kpinfo.py \
	$(PKGDIR)/translator_metakg.py \
	$(PKGDIR)/translator_query.py \
	$(PKGDIR)/translator_node.py \
	$(PKGDIR)/trapi.py \
	$(PKGDIR)/TCT_neighborhood_finder.py \
	$(PKGDIR)/TCT_pathfinder.py \
	$(PKGDIR)/TCT_network_annotator.py

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help apidoc Makefile

# Regenerate API stubs so new modules are documented automatically.
apidoc:
	@$(SPHINXAPIDOC) --separate --no-toc -q -o "$(APIDIR)" "$(PKGDIR)" $(APIDOC_EXCLUDE)

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile apidoc
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
