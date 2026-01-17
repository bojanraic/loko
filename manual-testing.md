# Manual Testing Checklist

Manual test scenarios for the `config` subcommand changes and loko-updater functionality. These complement the automated tests in `tests/test_cli_config.py` and `tests/test_upgrader.py`.

---

## Config Generate

### Scenario: Generate config in current directory
- **Steps:**
  1. Navigate to an empty directory
  2. Run `loko config generate`
  3. Verify `loko.yaml` is created
  4. Verify output shows detected local IP
- [ ] Pass / [ ] Fail

### Scenario: Generate config with custom output path
- **Steps:**
  1. Run `loko config generate --output my-config.yaml`
  2. Verify `my-config.yaml` is created (not `loko.yaml`)
  3. Verify file contains valid YAML with `environment` section
- [ ] Pass / [ ] Fail

### Scenario: Refuse overwrite without --force
- **Steps:**
  1. Run `loko config generate` to create `loko.yaml`
  2. Run `loko config generate` again (without --force)
  3. When prompted, type `n` to cancel
  4. Verify original file is unchanged
- [ ] Pass / [ ] Fail

### Scenario: Force overwrite existing file
- **Steps:**
  1. Create a file `loko.yaml` with custom content
  2. Run `loko config generate --force`
  3. Verify file is overwritten with new config template
- [ ] Pass / [ ] Fail

### Scenario: Verify auto-detected IP is correct
- **Steps:**
  1. Run `loko config generate`
  2. Check the displayed "Detected local IP" message
  3. Open generated `loko.yaml` and verify `network.ip` matches
  4. Verify IP is a valid local network IP (not 127.0.0.1 unless appropriate)
- [ ] Pass / [ ] Fail

---

## Config Validate

### Scenario: Validate a valid config file
- **Steps:**
  1. Generate a config: `loko config generate`
  2. Run `loko config validate`
  3. Verify output shows "✓ Configuration file 'loko.yaml' is valid"
  4. Verify environment name, Kubernetes version, and domain are displayed
- [ ] Pass / [ ] Fail

### Scenario: Validate with custom config path
- **Steps:**
  1. Generate config: `loko config generate --output custom.yaml`
  2. Run `loko config validate --config custom.yaml`
  3. Verify validation succeeds
- [ ] Pass / [ ] Fail

### Scenario: Validate missing config file
- **Steps:**
  1. Run `loko config validate --config nonexistent.yaml`
  2. Verify error message shows "Configuration file 'nonexistent.yaml' not found"
  3. Verify suggestions to use `--config` or `loko config generate` are shown
  4. Verify exit code is non-zero
- [ ] Pass / [ ] Fail

### Scenario: Validate config with invalid YAML syntax
- **Steps:**
  1. Create a file with invalid YAML: `echo "invalid: yaml: [" > bad.yaml`
  2. Run `loko config validate --config bad.yaml`
  3. Verify error indicates YAML parsing failure
  4. Verify exit code is non-zero
- [ ] Pass / [ ] Fail

### Scenario: Validate config with missing required fields
- **Steps:**
  1. Create minimal invalid config:
     ```yaml
     environment:
       name: test
     ```
  2. Run `loko config validate --config minimal.yaml`
  3. Verify error shows which fields are missing (e.g., cluster, network)
  4. Verify exit code is non-zero
- [ ] Pass / [ ] Fail

### Scenario: Validate displays workload counts
- **Steps:**
  1. Generate config and enable some workloads in `workloads.system`
  2. Run `loko config validate`
  3. Verify output shows correct count of enabled system and user workloads
- [ ] Pass / [ ] Fail

---

## Config Port-Check

### Scenario: Check ports with all available
- **Steps:**
  1. Ensure no services are using ports 53, 80, 443
  2. Generate a config: `loko config generate`
  3. Run `loko config port-check`
  4. Verify table shows all ports as "✓ Available"
  5. Verify summary shows "✓ All ports are available"
- [ ] Pass / [ ] Fail

### Scenario: Check ports with DNS port in use
- **Steps:**
  1. Start a service on port 53 (or use default system DNS)
  2. Generate config with `network.dns-port: 53`
  3. Run `loko config port-check`
  4. Verify DNS port shows "✗ In use"
  5. Verify exit code is non-zero
- [ ] Pass / [ ] Fail

### Scenario: Check ports with LB port in use
- **Steps:**
  1. Start a service on port 80 (e.g., `python -m http.server 80`)
  2. Run `loko config port-check`
  3. Verify Load Balancer port 80 shows "✗ In use"
  4. Verify troubleshooting commands are shown (lsof/netstat)
- [ ] Pass / [ ] Fail

### Scenario: Check ports with workload ports
- **Steps:**
  1. Edit config to enable postgres workload with port 5432
  2. Run `loko config port-check`
  3. Verify table shows "Workload" category with port 5432
  4. Verify "postgres" is shown in "Used By" column
- [ ] Pass / [ ] Fail

### Scenario: Check ports with custom config path
- **Steps:**
  1. Generate config: `loko config generate --output test.yaml`
  2. Run `loko config port-check --config test.yaml`
  3. Verify port check runs against the specified config
- [ ] Pass / [ ] Fail

### Scenario: Port-check with missing config
- **Steps:**
  1. Run `loko config port-check --config missing.yaml`
  2. Verify error shows config file not found
  3. Verify exit code is non-zero
- [ ] Pass / [ ] Fail

---

## Config Subcommand Help

### Scenario: Verify config subcommand help
- **Steps:**
  1. Run `loko config --help`
  2. Verify all subcommands are listed:
     - generate
     - validate
     - port-check
     - upgrade
     - helm-repo-add
     - helm-repo-remove
- [ ] Pass / [ ] Fail

### Scenario: Verify generate help
- **Steps:**
  1. Run `loko config generate --help`
  2. Verify `--output` / `-o` option is documented
  3. Verify `--force` / `-f` option is documented
- [ ] Pass / [ ] Fail

### Scenario: Verify validate help
- **Steps:**
  1. Run `loko config validate --help`
  2. Verify `--config` / `-c` option is documented
- [ ] Pass / [ ] Fail

### Scenario: Verify port-check help
- **Steps:**
  1. Run `loko config port-check --help`
  2. Verify `--config` / `-c` option is documented
- [ ] Pass / [ ] Fail

---

## Config Upgrade (loko-updater comments)

### Scenario: Generated config has loko-updater comments
- **Steps:**
  1. Run `loko config generate`
  2. Open the generated `loko.yaml`
  3. Verify comments use `# loko-updater:` format (not `# renovate:`)
  4. Check kubernetes tag, internal-components, and workloads sections
- [ ] Pass / [ ] Fail

### Scenario: Upgrade detects loko-updater comments
- **Steps:**
  1. Generate a config: `loko config generate`
  2. Run `loko config upgrade`
  3. Verify command scans and finds components to check
  4. Verify output shows version checks being performed
- [ ] Pass / [ ] Fail

### Scenario: Upgrade ignores old renovate comments
- **Steps:**
  1. Create a config with old `# renovate:` comment format:
     ```yaml
     cluster:
       kubernetes:
         image: kindest/node
         # renovate: datasource=docker depName=kindest/node
         tag: v1.32.0
     ```
  2. Run `loko config upgrade`
  3. Verify command reports "No components to check" (old format not recognized)
- [ ] Pass / [ ] Fail

### Scenario: Migration from renovate to loko-updater
- **Steps:**
  1. Create a config with old `# renovate:` comments
  2. Run migration command:
     ```bash
     sed -i '' 's/# renovate:/# loko-updater:/g' loko.yaml  # macOS
     ```
  3. Run `loko config upgrade`
  4. Verify components are now detected and checked
- [ ] Pass / [ ] Fail

### Scenario: Upgrade creates backup before changes
- **Steps:**
  1. Generate a config with outdated versions
  2. Run `loko config upgrade`
  3. Verify `loko-prev.yaml` backup file is created
  4. Verify backup contains original versions
- [ ] Pass / [ ] Fail

### Scenario: Upgrade with no updates available
- **Steps:**
  1. Generate a fresh config (should have latest versions)
  2. Run `loko config upgrade`
  3. Verify output shows "All versions are up to date"
  4. Verify no backup file is created (no changes made)
- [ ] Pass / [ ] Fail

### Scenario: Upgrade preserves YAML formatting
- **Steps:**
  1. Generate config and add custom comments/formatting
  2. Run `loko config upgrade`
  3. Verify custom comments are preserved
  4. Verify loko-updater comments are preserved
  5. Verify indentation and structure unchanged
- [ ] Pass / [ ] Fail

### Scenario: Upgrade with network error
- **Steps:**
  1. Disconnect from network or block Docker Hub/Helm repos
  2. Run `loko config upgrade`
  3. Verify graceful error handling (no crash)
  4. Verify partial updates still work (if some sources accessible)
- [ ] Pass / [ ] Fail

---

## Backward Compatibility

### Scenario: Old generate-config command is removed
- **Steps:**
  1. Run `loko generate-config`
  2. Verify command is not found / shows error
  3. Verify `loko --help` does not list `generate-config`
- [ ] Pass / [ ] Fail

### Scenario: Error message references new command
- **Steps:**
  1. Delete any existing `loko.yaml`
  2. Run `loko init`
  3. Verify error message suggests `loko config generate` (not `generate-config`)
- [ ] Pass / [ ] Fail

---

## Integration Workflows

### Scenario: Full workflow - generate, validate, port-check, create
- **Steps:**
  1. `loko config generate`
  2. `loko config validate`
  3. `loko config port-check`
  4. `loko create` (if Docker available and ports free)
  5. Verify each step succeeds
- [ ] Pass / [ ] Fail

### Scenario: Validate after manual config edits
- **Steps:**
  1. `loko config generate`
  2. Manually edit `loko.yaml` (change domain, add workloads, etc.)
  3. `loko config validate`
  4. Verify validation catches any errors or confirms valid config
- [ ] Pass / [ ] Fail

### Scenario: Port-check before cluster creation
- **Steps:**
  1. `loko config generate`
  2. `loko config port-check`
  3. If any ports in use, stop conflicting services
  4. Re-run `loko config port-check` to confirm all clear
  5. `loko create`
- [ ] Pass / [ ] Fail

---

## Edge Cases

### Scenario: Config with environment variable expansion
- **Steps:**
  1. Generate config with `base-dir: $HOME/.loko`
  2. Set `expand-env-vars: true`
  3. Run `loko config validate`
  4. Verify validation succeeds (env var expansion works)
- [ ] Pass / [ ] Fail

### Scenario: Config with unicode characters
- **Steps:**
  1. Edit config to include unicode in `name` field
  2. Run `loko config validate`
  3. Verify no encoding errors
- [ ] Pass / [ ] Fail

### Scenario: Port-check with high port numbers
- **Steps:**
  1. Edit config to use non-standard ports (e.g., 8080, 8443)
  2. Run `loko config port-check`
  3. Verify high ports are checked correctly
- [ ] Pass / [ ] Fail

---

## Notes

- All tests assume `loko` is installed and available in PATH
- Docker must be running for `loko create` tests
- Some port tests may require elevated privileges to bind to low ports
- Test on both macOS and Linux if possible
- **Breaking Change**: `# renovate:` comments are no longer recognized; use `# loko-updater:` instead
- Migration command: `sed -i '' 's/# renovate:/# loko-updater:/g' loko.yaml` (macOS) or `sed -i 's/# renovate:/# loko-updater:/g' loko.yaml` (Linux)
