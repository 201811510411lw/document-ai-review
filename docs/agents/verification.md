# Fast Verification Workflow

## Objective

Keep routine fixes fast while preserving real UAT evidence. Local verification answers whether the changed module behaves as intended. Jenkins answers whether the image can be built. UAT acceptance answers whether the deployed OA workflow actually works.

Do not repeat the same full compilation or test suite at local, Jenkins, and deployment stages.

## Default Local Verification

Choose the smallest command that covers the changed behavior:

| Change scope | Required local verification |
| --- | --- |
| Documentation or Agent Skill only | `make verify-docs` |
| Python implementation | `make verify-python` plus directly affected tests |
| OA tobacco consistency | `make verify-oa-tobacco` |
| Web Console | `make verify-frontend` |
| One specific regression | `make verify-test TESTS='tests/test_file.py::test_name'` |
| Mixed backend and frontend change | Run the relevant backend target and `make verify-frontend` |

Run focused verification once after the complete functional change. Do not rerun it after every file edit unless the result is needed to continue implementation.

`make verify-full` is a diagnostic command only. Do not run it by default and do not use it as a commit, image-build, or deployment gate. Run it only when the user explicitly requests a full suite or when investigating a cross-domain failure that cannot be isolated with focused tests.

## Jenkins Image Build

Jenkins builds the image once from the requested Git commit. A successful build proves dependency installation, frontend production compilation, and image assembly. Do not repeat a local production build solely because Jenkins will perform the same build.

While the project remains in its testing stage, every Jenkins image build and test deployment uses the image tag `v1`. Do not generate a Git SHA, build number, timestamp, or semantic version as a new image tag, and do not create a Git tag solely for a test deployment, unless the user explicitly requests one or declares a production release.

Record the source commit and resulting image identity. A mutable tag such as `v1` is not sufficient evidence by itself; use the image label, digest, or running container image ID to correlate the deployment with the commit.

## UAT Acceptance

After deployment, verify the behavior that changed against the deployed image. Deployment acceptance replaces repeated local full-suite execution; it is not replaced by `RUNNING`, HTTP 200, or a successful image build.

For OA tobacco changes:

1. Confirm the running workload uses the image built from the intended commit.
2. Submit a new OA request, or perform a real OA return and resubmission; the caller does not provide `submission_version`.
3. Correlate the derived `submission_log_id` and `submission_version` with the persisted review task and callback history.
4. Inspect the actual callback JSON, including the domain decision, reason text, structured differences, suggestions, and retryability.
5. Confirm the callback receiver accepted the business result, not only the HTTP transport.
6. Confirm OA reached the expected node or returned to the expected applicant step.

If UAT fails, add or refine the smallest regression test that reproduces that failure, fix it, rebuild once, and repeat with another new request ID or another real OA resubmission event.

## Reporting

Report these boundaries separately:

- focused local verification;
- Git commit and remote publication;
- Jenkins image build and image identity;
- deployed workload provenance;
- UAT business acceptance.

Do not describe one boundary as proof of another.
