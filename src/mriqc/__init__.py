"""
MRIQC (MRI Quality Control) module.

Handles running MRIQC via Docker and parsing its output metrics:
  - runner:      Docker-based MRIQC execution (participant + group level)
  - iqm_parser:  Image Quality Metrics (IQM) JSON parser & flagging
"""

from .runner import (
    run_mriqc_participant,
    run_mriqc_group,
    collect_mriqc_reports,
    mriqc_preflight,
    get_docker_vm_resources,
)
from .iqm_parser import parse_all_subjects, IQMResult, IQMFlag, METRIC_DISPLAY

__all__ = [
    "run_mriqc_participant",
    "run_mriqc_group",
    "collect_mriqc_reports",
    "mriqc_preflight",
    "get_docker_vm_resources",
    "parse_all_subjects",
    "IQMResult",
    "IQMFlag",
    "METRIC_DISPLAY",
]
