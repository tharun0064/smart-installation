# Common Failures - OTel OracleDB Receiver

## ORA-12541: TNS:no listener
- Oracle listener not running on target host
- Fix: `sudo lsnrctl start` on DB server, or check listener.ora

## ORA-12514: TNS:listener does not know of service
- SERVICE_NAME in tnsnames.ora doesn't match DB service
- Fix: Verify with `lsnrctl services` and update tnsnames.ora

## ORA-01017: invalid username/password
- Monitoring user credentials incorrect
- Fix: Reset password with `ALTER USER otel_monitor IDENTIFIED BY <new_pass>`

## libclntsh.so: cannot open shared object file
- Oracle Instant Client not in LD_LIBRARY_PATH
- Fix: `export LD_LIBRARY_PATH=$ORACLE_HOME/lib:$LD_LIBRARY_PATH`

## Connection timed out to otlp.nr-data.net:4317
- Firewall blocking outbound gRPC to New Relic
- Fix: `sudo ufw allow out 4317/tcp` or whitelist in security group

## otelcol-contrib.service: Failed with result 'exit-code'
- Config file syntax error or missing env vars
- Fix: Run `otelcol-contrib validate --config /etc/otelcol-contrib/config.yaml`
