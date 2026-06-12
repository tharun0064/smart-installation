# Prerequisites for OTel OracleDB Receiver

## Oracle Instant Client
- Must be installed at $ORACLE_HOME
- libclntsh.so must be accessible
- LD_LIBRARY_PATH must include $ORACLE_HOME/lib

## TNS Configuration
- TNS_ADMIN must point to directory containing tnsnames.ora
- tnsnames.ora must have entry for the target database
- listener.ora must be configured on the DB server

## Database User
- Requires a monitoring user with grants:
  ```sql
  CREATE USER otel_monitor IDENTIFIED BY <password>;
  GRANT CONNECT TO otel_monitor;
  GRANT SELECT_CATALOG_ROLE TO otel_monitor;
  ```

## Network
- Port 1521 (or custom listener port) must be accessible from this host
- Firewall must allow outbound to otlp.nr-data.net:4317
