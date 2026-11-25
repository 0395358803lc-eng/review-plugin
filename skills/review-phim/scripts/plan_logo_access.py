#!/usr/bin/env python3
"""Plan a least-privilege Desktop Commander LOGO_ROOT allowlist update.

Pure planning utility: NEVER changes Desktop Commander settings, NTFS ACLs,
or any filesystem permissions. The agent must call get_config and
set_config_value on the same selected link_id and deviceId, then verify.
"""
from __future__ import annotations

import argparse
import json
import ntpath
import posixpath
import re
from pathlib import Path


def _platform_path(value: str, *, allow_root: bool = False) -> tuple[str, str]:
    """Canonical *text* only. On-device realpath and actual directory access
    must be verified separately before binding.
    """
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError('LOGO_PATH_INVALID: choose an existing absolute folder')
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if any(ch in value for ch in ('*', '?')):
        raise ValueError('LOGO_PATH_WILDCARD_FORBIDDEN')
    if re.match(r'^[a-zA-Z]:', value) or value.startswith(('\\\\', '//')):
        if not ntpath.isabs(value):
            raise ValueError('LOGO_PATH_ABSOLUTE_REQUIRED')
        clean = ntpath.normpath(value)
        anchor = ntpath.splitdrive(clean)[0]
        # A drive root or UNC share root is too broad to be added automatically.
        if not allow_root and ntpath.normcase(clean.rstrip('\\/')) == ntpath.normcase(anchor.rstrip('\\/')):
            raise ValueError('LOGO_PATH_TOO_BROAD: choose a folder, not the drive/share root')
        if not allow_root and ntpath.splitdrive(clean)[1] in ('', '\\', '/'):
            raise ValueError('LOGO_PATH_TOO_BROAD: choose a folder, not the drive/share root')
        return 'windows', clean
    if value.startswith('/'):
        clean = posixpath.normpath(value)
        if not allow_root and clean == '/':
            raise ValueError('LOGO_PATH_TOO_BROAD: select a folder, not the filesystem root')
        return 'posix', clean
    raise ValueError('LOGO_PATH_ABSOLUTE_REQUIRED')


def _contains(existing: str, requested: str, style: str) -> bool:
    try:
        other_style, original = _platform_path(existing, allow_root=True)
        if other_style != style:
            return False
        module = ntpath if style == 'windows' else posixpath
        # normcase is case-insensitive only on Windows.
        return module.commonpath((original, requested)) == original if style == 'posix' else (
            module.normcase(module.commonpath((original, requested))) == module.normcase(original)
        )
    except (ValueError, TypeError):
        # Existing historical entries are not repaired or silently removed.
        return False


def plan_logo_access(config: dict, logo_root: str) -> dict:
    """Return exact proposed allowedDirectories without applying it.

    [] means full filesystem access in Desktop Commander, so NEVER propose []
    as a way to fix a path that is blocked. Retain all pre-existing entries.
    """
    if not isinstance(config, dict) or 'allowedDirectories' not in config:
        raise ValueError('DC_CONFIG_UNVERIFIED: allowedDirectories missing; do not change configuration')
    previous = config['allowedDirectories']
    if not isinstance(previous, list) or any(not isinstance(item, str) for item in previous):
        raise ValueError('DC_CONFIG_INVALID: expected allowedDirectories as list of paths')
    style, chosen = _platform_path(logo_root)
    if not previous:
        return {
            'status': 'already_unrestricted',
            'requires_config_change': False,
            'logo_root_requested': chosen,
            'allowedDirectories': [],
            'message': 'Desktop Commander already has an unrestricted allowlist; if access is denied, check another policy layer/OS permissions, not this list.',
        }
    if any(_contains(existing, chosen, style) for existing in previous):
        return {
            'status': 'already_allowed',
            'requires_config_change': False,
            'logo_root_requested': chosen,
            'allowedDirectories': list(previous),
        }
    return {
        'status': 'needs_directory_allowlist_update',
        'requires_config_change': True,
        'logo_root_requested': chosen,
        'allowedDirectories': [*previous, chosen],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config-file', required=True, type=Path)
    p.add_argument('--logo-root', required=True)
    a = p.parse_args()
    conf = json.loads(a.config_file.read_text(encoding='utf-8'))
    print(json.dumps(plan_logo_access(conf, a.logo_root), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
