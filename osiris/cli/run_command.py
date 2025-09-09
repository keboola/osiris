"""Temporary placeholder for run command import."""


def run_command(args):
    """Import and execute the new run command."""
    from .run import run_command as new_run_command

    new_run_command(args)
