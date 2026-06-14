# Common Failures

## wget/curl not installed
- Bare Linux containers often don't have wget pre-installed
- Fix: `apt-get update && apt-get install -y wget curl`

## Cannot connect to Oracle Database (port 1521 unreachable)
- Oracle listener is not running: `lsnrctl start`
- Firewall blocking port: check iptables/ufw rules
- Wrong hostname: verify ORACLE_HOST resolves correctly
- Container networking: containers on different Docker networks cannot reach each other
- Fix for Docker: `docker network connect <network-name> <container-name>`

## ORA-01017: invalid username/password; logon denied
- Wrong credentials in /etc/otelcol-contrib/config.yaml or environment variables
- User does not exist in the Oracle database
- Password expired or account locked
- Fix: verify credentials with `sqlplus username/password@host:port/service`
- Update credentials in /etc/otelcol-contrib/config.yaml and restart collector

## ORA-01031: insufficient privileges
- The monitoring user needs SELECT privileges on V$ views
- Fix: `GRANT SELECT ON V_$SESSION TO monitoring_user;`
- Required grants: V_$SYSSTAT, V_$SYSTEM_EVENT, DBA_TABLESPACES, DBA_DATA_FILES

## YAML configuration errors
- Invalid indentation (YAML requires consistent spacing)
- Unknown configuration keys (typos in receiver/processor/exporter names)
- References to undefined components in pipeline
- Fix: run `otelcol-contrib validate --config=/etc/otelcol-contrib/config.yaml`
- Check YAML syntax with proper 2-space indentation

## Collector starts but no metrics in New Relic
- Invalid or missing NEW_RELIC_LICENSE_KEY
- Wrong OTLP endpoint URL
- Verify connectivity: `curl -v https://otlp.nr-data.net`
- Check collector logs: `journalctl -u otelcol-contrib -f`

## Architecture mismatch (wrong binary downloaded)
- Container architecture (arm64 vs amd64) doesn't match downloaded binary
- Check with: `uname -m` (aarch64 = arm64, x86_64 = amd64)
- Download the correct architecture variant
