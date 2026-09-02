PYTHON ?= /home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python
PYTEST ?= /home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest

OA_TOBACCO_TESTS = \
	tests/test_oa_tobacco_auto_review_api.py \
	tests/test_tobacco_consistency_extraction.py \
	tests/test_tobacco_license_consistency_use_case.py \
	tests/test_tobacco_report_list.py

.PHONY: verify-diff verify-docs verify-python verify-test verify-oa-tobacco verify-frontend verify-full

verify-diff:
	git diff --check

verify-docs: verify-diff

verify-python: verify-diff
	$(PYTHON) -m compileall -q ai-service/app ai-service/tests

verify-test: verify-python
	@test -n "$(TESTS)" || (echo "TESTS is required, for example: make verify-test TESTS='tests/test_review_service.py'" && exit 2)
	cd ai-service && $(PYTEST) $(TESTS) -q

verify-oa-tobacco: verify-python
	cd ai-service && $(PYTEST) $(OA_TOBACCO_TESTS) -q

verify-frontend: verify-diff
	cd web-console && npm test

# Diagnostic command only. It is not a commit, image-build, or deployment gate.
verify-full: verify-python
	cd ai-service && $(PYTEST) -q
	cd web-console && npm test
	cd web-console && npm run build
