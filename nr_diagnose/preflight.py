"""Pre-flight config validation - validates environment variables and connectivity."""

import os
import re
from typing import List, Optional, Tuple

from .diagnostics import check_connectivity, check_dns
from .registry import Agent as RegistryAgent
from .schemas import ConfigVar, PreflightResult
from . import ui

ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::-[^}]*)?\}")


def extract_config_vars(command: str) -> List[ConfigVar]:
    """Extract environment variables from a command and infer their validation type."""
    var_names = list(set(ENV_VAR_PATTERN.findall(command)))
    config_vars = []

    for name in sorted(var_names):
        vtype = _infer_type(name)
        current = os.environ.get(name, "")
        config_vars.append(ConfigVar(
            name=name,
            current_value=current,
            required=True,
            validation_type=vtype,
        ))

    return config_vars


def validate_var(var: ConfigVar) -> Tuple[bool, str]:
    """Validate a single config variable. Returns (ok, error_message)."""
    value = var.current_value

    if not value:
        return False, f"{var.name} is not set"

    if var.validation_type == "port":
        try:
            port = int(value)
            if not (1 <= port <= 65535):
                return False, f"{var.name}={value} is not a valid port (1-65535)"
        except ValueError:
            return False, f"{var.name}={value} is not a number"

    elif var.validation_type == "license_key":
        if len(value) < 30:
            return False, f"{var.name} looks too short for a license key (got {len(value)} chars, expected 30+)"

    elif var.validation_type == "host":
        if " " in value or "\t" in value:
            return False, f"{var.name}={value!r} contains whitespace"

    return True, ""


def run_connectivity_checks(
    vars_validated: dict, manifest_ports: List[int]
) -> dict:
    """Run connectivity checks for host+port pairs. Returns {description: passed}."""
    results = {}

    hosts = {}
    ports = {}
    for name, value in vars_validated.items():
        if _infer_type(name) == "host":
            hosts[name] = value
        elif _infer_type(name) == "port":
            try:
                ports[name] = int(value)
            except ValueError:
                pass

    # Match hosts with ports by prefix (e.g., ORACLE_HOST + ORACLE_PORT)
    for host_var, host_val in hosts.items():
        prefix = host_var.replace("_HOST", "").replace("_HOSTNAME", "")
        port_val = None

        # Find matching port var
        for port_var, pv in ports.items():
            if port_var.startswith(prefix):
                port_val = pv
                break

        # Fall back to manifest ports
        if port_val is None and manifest_ports:
            port_val = manifest_ports[0]

        if port_val:
            # DNS check
            dns_ok, dns_output = check_dns(host_val)
            results[f"DNS resolve {host_val}"] = dns_ok

            # Connectivity check
            conn_ok, conn_output = check_connectivity(host_val, port_val)
            results[f"Connect to {host_val}:{port_val}"] = conn_ok
        else:
            dns_ok, _ = check_dns(host_val)
            results[f"DNS resolve {host_val}"] = dns_ok

    return results


def run_preflight(
    command: str, agent_info: Optional[RegistryAgent]
) -> PreflightResult:
    """Run full pre-flight validation for a config-writing step.

    Extracts env vars, prompts user for values, validates them,
    and runs connectivity checks.
    """
    config_vars = extract_config_vars(command)

    if not config_vars:
        return PreflightResult(passed=True)

    errors = []
    vars_validated = {}

    # Prompt user for each variable
    for var in config_vars:
        value = ui.prompt_config_var(var.name, var.current_value, var.validation_type)

        # Update env so the step will use the new value
        if value:
            os.environ[var.name] = value
            var.current_value = value

        # Validate
        ok, err_msg = validate_var(var)
        ui.show_preflight_check(f"{var.name} = {_mask_value(value, var.validation_type)}", ok)
        if ok:
            vars_validated[var.name] = var.current_value
        else:
            errors.append(err_msg)

    # Connectivity checks
    manifest_ports = agent_info.manifest.ports if agent_info else []
    connectivity = run_connectivity_checks(vars_validated, manifest_ports)

    for desc, passed in connectivity.items():
        ui.show_preflight_check(desc, passed)
        if not passed:
            errors.append(f"Connectivity failed: {desc}")

    result = PreflightResult(
        passed=len(errors) == 0,
        vars_validated=vars_validated,
        connectivity_results=connectivity,
        errors=errors,
    )

    ui.show_preflight_summary(result)
    return result


def _infer_type(name: str) -> str:
    """Infer validation type from variable name conventions."""
    upper = name.upper()
    if upper.endswith("_HOST") or upper.endswith("_HOSTNAME"):
        return "host"
    elif upper.endswith("_PORT"):
        return "port"
    elif "LICENSE_KEY" in upper or "API_KEY" in upper:
        return "license_key"
    elif "PASSWORD" in upper or "PASSWD" in upper or "SECRET" in upper:
        return "password"
    return "string"


def _mask_value(value: str, validation_type: str) -> str:
    """Mask sensitive values for display."""
    if not value:
        return "[not set]"
    if validation_type in ("password", "license_key"):
        if len(value) > 6:
            return value[:3] + "***" + value[-3:]
        return "***"
    return value
