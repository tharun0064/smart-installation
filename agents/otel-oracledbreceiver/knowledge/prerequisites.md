# Prerequisites

- Oracle Database 12c or higher must be running and accessible
- Oracle listener must be active on port 1521
- A database user with monitoring privileges (SELECT on V$SESSION, V$SYSSTAT, DBA_TABLESPACES, etc.)
- Network connectivity from the collector host to the Oracle DB host on port 1521
- Network connectivity to https://otlp.nr-data.net (New Relic OTLP endpoint)
- A valid New Relic License Key (ingest type, starts with NRII or similar)
