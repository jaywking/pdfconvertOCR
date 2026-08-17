<!--
Source: dev-toolbox/standards/AUTOMATION_STANDARD.md
Standard-Version: 1.1.0
Last-Updated: 2026-08-16
Managed-By: dev-toolbox
Managed-Mode: WholeFile
Local-Overrides: PROJECT_CONTEXT.md
-->

# Automation Standard

## Operating Contract

- Define the inputs, outputs, side effects, success conditions, and failure
  behavior before implementation.
- Keep the normal path silent and headless unless interaction is explicitly
  required.
- Do not depend on GUI prompts, Save As dialogs, virtual printers, an unlocked
  desktop, or a manually prepared shell session.
- Prefer direct command-line tools, stable APIs, and maintained libraries.

## Inputs, Outputs, and File Safety

- Validate input existence, type, accessibility, and expected format before
  processing.
- Use explicit source, staging, completed, processed-original, and log paths.
  Record project-specific paths in `PROJECT_CONTEXT.md`.
- Preserve originals until the final output exists and passes required
  validation.
- Write to a temporary or staging file and move it into place atomically where
  practical.
- Avoid silent overwrites. Require an explicit policy for replace, skip,
  version, or fail behavior.
- Make reruns idempotent where practical and document any non-idempotent step.
- Do not use cloud-only or synchronized folders unless that behavior is
  intentional and documented.

## Validation and Requirements

- Check required executables, modules, versions, configuration, free space, and
  permissions before beginning consequential work.
- Pin project-owned dependencies and document supported runtime versions. For
  projects under `C:\Utils`, keep the generated Python environment under
  `C:\LocalVenvs\<project>` by default and keep its reproducibility files in
  the project.
- Treat external project environments as disposable. Record creation, install,
  and validation commands, and do not silently rebuild or upgrade them.
- Resolve executable paths deterministically. Do not assume a user-specific
  PATH is present in scheduled tasks.
- Validate output content, not only output-file existence.

## Logging

- Use timestamped logs with a consistent, parseable structure.
- Record start time, finish time, operation, input, output, duration, result,
  warnings, and failure details where applicable.
- Include enough information for diagnosis without logging credentials,
  tokens, sensitive content, or unnecessary personal data.
- Write a final summary with success, skipped, warning, and failed counts for
  batch work.

## Errors and Exit Behavior

- Stop or isolate work safely when prerequisites fail.
- Use actionable error messages that identify the failed step and affected
  item.
- Return meaningful exit codes for scripts used by schedulers or other tools.
- Do not move an original to a processed folder after a failed or unverified
  conversion.
- Clean up temporary files without deleting source material.

## Preview, Backup, and Rollback

- Provide a dry-run or preview mode for destructive, bulk, or externally
  visible changes where practical.
- Make preview output identify exact targets and intended actions.
- Back up replaceable configuration or maintained data before risky updates.
- Document the rollback path and test it when failure would be costly.

## Windows and Scheduled Tasks

- Use robust literal-path handling and quote paths containing spaces.
- Account for execution policy, file permissions, user profiles, working
  directories, service accounts, mapped drives, and noninteractive sessions.
- Use absolute paths for scheduled-task entry points and required executables.
- Invoke the project's explicit
  `C:\LocalVenvs\<project>\Scripts\python.exe` path rather than relying on
  activation, the default Python, or global PATH changes.
- Ensure logs and exit codes remain available when no console is visible.

## Acceptance

An automation change is complete only when its expected output, failure path,
logging, preservation of originals, rerun behavior, and unattended execution
have been verified in proportion to risk.
