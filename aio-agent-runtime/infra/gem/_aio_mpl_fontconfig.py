"""
AIO Sandbox: matplotlib fontconfig bridge.

matplotlib has its own font_manager that does NOT use fontconfig.
When a font is not in its cache (e.g. SimHei), it silently falls back to
the "best scoring" available font (e.g. Liberation Sans) — no exception,
just wrong glyphs.

This module patches FontManager.findfont() with two layers of fallback:

1. fc-match resolution: if requested fonts (e.g. SimHei) are not in
   matplotlib's cache, resolve them via fontconfig (which respects our
   alias config in 99-font-aliases.conf).

2. CJK fallback injection: if the resolved font list contains NO CJK-capable
   fonts (e.g. after plt.style.use() overwrites user's CJK settings with
   Western-only fonts), inject a CJK fallback so Chinese/Japanese/Korean
   text renders correctly instead of showing tofu blocks.

Installed at Python startup via a .pth file.
"""

import os
import subprocess
import sys

_fc_cache = {}

# CJK fallback fonts to inject when no CJK font is in the resolved list.
_CJK_FALLBACK_FAMILIES = ["Noto Sans CJK SC", "WenQuanYi Micro Hei"]

# Substrings that indicate a font family name is CJK-capable.
_CJK_INDICATORS = frozenset({
    "cjk", "wenquanyi", "wqy", "ar pl",
    "simhei", "simsun", "microsoft yahei", "kaiti", "fangsong",
    "dengxian", "stheiti", "stsong", "stkaiti", "stfangsong",
    "pingfang", "hiragino", "meiryo", "yu gothic", "yu mincho",
    "malgun", "gulim", "dotum", "batang", "nsimsun",
})


def _fc_match(family):
    """Resolve a font family name to a file path via fontconfig."""
    if family in _fc_cache:
        return _fc_cache[family]
    try:
        proc = subprocess.run(
            ["fc-match", "-f", "%{file}", family],
            capture_output=True, text=True, timeout=5,
        )
        path = proc.stdout.strip()
        if path and os.path.isfile(path):
            _fc_cache[family] = path
            return path
    except Exception:
        pass
    _fc_cache[family] = None
    return None


def _has_cjk_font(families):
    """Check if any family name in the list is likely CJK-capable."""
    for f in families:
        fl = f.lower()
        if any(ind in fl for ind in _CJK_INDICATORS):
            return True
    return False


def _resolve_families(prop):
    """Extract concrete font names, resolving aliases like 'sans-serif'."""
    import matplotlib

    if isinstance(prop, str):
        raw = [prop]
    elif hasattr(prop, "get_family"):
        raw = prop.get_family()
    else:
        return []

    _ALIASES = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
    resolved = []
    for family in raw:
        if family.lower() in _ALIASES:
            resolved.extend(matplotlib.rcParams.get(f"font.{family}", []))
        else:
            resolved.append(family)
    return resolved


def _patch_findfont(fm_module):
    """Patch FontManager to resolve missing fonts via fontconfig."""
    FontManager = fm_module.FontManager
    _original = FontManager.findfont

    # Build a set of known font family names from matplotlib's cache
    _known_cache = {}

    def _get_known_families(fm_instance):
        """Lazily build set of font families known to matplotlib."""
        fid = id(fm_instance)
        if fid not in _known_cache:
            _known_cache[fid] = {
                entry.name.lower()
                for entry in getattr(fm_instance, "ttflist", [])
            }
        return _known_cache[fid]

    def _patched(self, prop, fontext="ttf", directory=None,
                 fallback_to_default=True, rebuild_if_missing=True):
        resolved = _resolve_families(prop)
        known = _get_known_families(self)

        # Phase 1: CJK fallback injection (must run BEFORE fc-match).
        # Handles: plt.style.use('seaborn-v0_8') overwrites font.sans-serif
        # to ['Arial', 'Liberation Sans', ...] — all Western, no CJK.
        # If we let fc-match run first, it resolves 'Arial' → Liberation Sans
        # and returns immediately, never reaching this check.
        if not _has_cjk_font(resolved):
            for cjk in _CJK_FALLBACK_FAMILIES:
                if cjk.lower() in known:
                    from matplotlib.font_manager import FontProperties
                    return _original(
                        self, FontProperties(family=[cjk]),
                        fontext=fontext,
                        directory=directory,
                        fallback_to_default=fallback_to_default,
                        rebuild_if_missing=rebuild_if_missing,
                    )

        # Phase 2: fc-match for fonts not in matplotlib's cache.
        # Handles: rcParams['font.sans-serif'] = ['SimHei'] where SimHei
        # is not installed but fontconfig can alias it to Noto Sans CJK SC.
        for family in resolved:
            if family.lower() not in known:
                fc_path = _fc_match(family)
                if fc_path:
                    return fc_path

        # All requested fonts are in cache — use original scoring.
        return _original(
            self, prop,
            fontext=fontext,
            directory=directory,
            fallback_to_default=fallback_to_default,
            rebuild_if_missing=rebuild_if_missing,
        )

    FontManager.findfont = _patched

    # Critical: also update the module-level shortcut.
    # font_manager.py line 1644 does `findfont = fontManager.findfont` which
    # captures a bound method to the ORIGINAL findfont. Replacing the class
    # attribute above does NOT update that reference. Rendering code (e.g.
    # _mathtext.py) imports this module-level `findfont` and would bypass
    # our patch without this line.
    if hasattr(fm_module, "fontManager"):
        fm_module.findfont = fm_module.fontManager.findfont


def _install():
    """Register a one-shot import hook for matplotlib.font_manager."""

    class _Hook:
        _active = True

        def find_module(self, fullname, path=None):
            if fullname == "matplotlib.font_manager" and self._active:
                return self
            return None

        def load_module(self, fullname):
            self.__class__._active = False
            sys.meta_path[:] = [h for h in sys.meta_path if h is not self]

            if fullname in sys.modules:
                _patch_findfont(sys.modules[fullname])
                return sys.modules[fullname]

            import importlib
            mod = importlib.import_module(fullname)
            _patch_findfont(mod)
            return mod

    sys.meta_path.insert(0, _Hook())


_install()
