"""TUI screen components."""

from gltools.tui.screens.ci_status import CIStatusScreen
from gltools.tui.screens.dashboard import DashboardPanel, DashboardScreen, ItemSelected
from gltools.tui.screens.issue_detail import IssueDetailScreen
from gltools.tui.screens.issue_list import IssueListScreen
from gltools.tui.screens.mr_detail import MRDetailScreen
from gltools.tui.screens.mr_list import MRListScreen

__all__ = [
    "CIStatusScreen",
    "DashboardPanel",
    "DashboardScreen",
    "IssueDetailScreen",
    "IssueListScreen",
    "ItemSelected",
    "MRDetailScreen",
    "MRListScreen",
]
