# Demo Scenarios

Each scenario demonstrates a different failure mode that the AI diagnostics engine can handle.

## Setup

```bash
# From project root:
cd demo

# 1. Start Oracle DB (prerequisite for all scenarios)
./scenario-1-setup.sh

# Wait for "Oracle DB is ready!" message (~60 seconds first time)
```

## Scenarios

Run each scenario one at a time:

| # | Script | Failure Mode | What AI Does |
|---|--------|-------------|--------------|
| 1 | `scenario-1-setup.sh` | N/A (setup) | Starts OracleDB container |
| 2 | `scenario-2-prereqs.sh` | `wget: command not found` | Detects missing tool, suggests `apt-get install -y wget` |
| 3 | `scenario-3-network.sh` | `nc: connect failed` (port unreachable) | Runs ping/nc diagnostics, identifies Docker network isolation |
| 4 | `scenario-4-badconfig.sh` | YAML parse error on validate | Reads config, identifies indentation/key errors, suggests fix |
| 5 | `scenario-5-badcreds.sh` | `ORA-01017: invalid username/password` | Detects auth failure in logs, asks user to update credentials |

## Running a Scenario

```bash
./scenario-2-prereqs.sh
```

Each scenario:
1. Builds the `nr-diagnose` Docker image
2. Starts a container with the specific failure condition
3. Runs `nr-diagnose run --agent otel-oracledbreceiver` inside
4. You interact with the AI (approve/reject fixes)
5. Container is removed when done

## Cleanup

```bash
./cleanup.sh
```

Removes all demo containers and the Docker network.

## Oracle DB Details

- **Host:** `oracledb` (Docker DNS on demo-net)
- **Port:** 1521
- **Service:** XEPDB1
- **System user:** system / demo_password_123
- **App user:** monitoring_user / monitor_pass_123
