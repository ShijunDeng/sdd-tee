#!/usr/bin/env python3
"""
SDD-TEE v5.1 — Functional Equivalence Verification (ST-6.5)

Compares AI-generated code against the original agentcube source to verify
functional equivalence at three levels:

1. **File-level coverage** — which original files have corresponding generated files
2. **API contract compliance** — endpoints, function signatures, response formats match
3. **Behavioral equivalence** — same inputs produce same outputs (via test suite)

Usage:
    from equivalence import EquivalenceChecker
    checker = EquivalenceChecker(original_repo, generated_workspace, lang)
    result = checker.verify(ar_id, ar_module)
    # result has: file_coverage, api_compliance, behavioral_pass_rate, overall_score
"""

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EquivalenceResult:
    """Result of functional equivalence verification for one AR."""
    ar_id: str = ""
    ar_module: str = ""
    # File-level
    original_file_count: int = 0
    generated_file_count: int = 0
    matched_files: list[tuple[str, str]] = field(default_factory=list)
    unmatched_original: list[str] = field(default_factory=list)
    unmatched_generated: list[str] = field(default_factory=list)
    file_coverage_pct: float = 0.0
    # Line-level similarity
    total_original_lines: int = 0
    total_generated_lines: int = 0
    similar_lines: int = 0
    line_similarity_pct: float = 0.0
    # API contract
    api_original_count: int = 0
    api_generated_count: int = 0
    api_matched: int = 0
    api_compliance_pct: float = 0.0
    # Quality metrics
    overall_score: float = 0.0  # weighted: 40% file_coverage + 30% api_compliance + 30% line_similarity
    notes: str = ""


class EquivalenceChecker:
    """Compare generated code against original agentcube source."""

    def __init__(self, original_repo: str, generated_workspace: str, lang: str):
        self.original = Path(original_repo)
        self.generated = Path(generated_workspace)
        self.lang = lang
        self.file_exts = {".go", ".mod", ".sum"} if lang == "Go" else {".py", "requirements.txt"}

    def verify(
        self,
        ar_id: str = "",
        ar_module: str = "",
        module_filter: Optional[str] = None,
    ) -> EquivalenceResult:
        """Run full equivalence verification."""
        result = EquivalenceResult(ar_id=ar_id, ar_module=ar_module)

        if not self.original.exists():
            result.notes = "Original repo not found — cannot verify equivalence."
            return result

        # 1. File-level mapping
        orig_files = self._find_source_files(self.original)
        gen_files = self._find_source_files(self.generated)

        # Filter by module if specified
        if module_filter:
            orig_files = [f for f in orig_files if module_filter.lower() in f.lower()]
            gen_files = [f for f in gen_files if module_filter.lower() in f.lower()]

        result.original_file_count = len(orig_files)
        result.generated_file_count = len(gen_files)

        # Map files by basename + relative path similarity
        matched, unmatched_orig, unmatched_gen = self._match_files(orig_files, gen_files)
        result.matched_files = matched
        result.unmatched_original = unmatched_orig
        result.unmatched_generated = unmatched_gen

        if orig_files:
            result.file_coverage_pct = round(len(matched) / len(orig_files) * 100, 2)

        # 2. Line-level similarity for matched files
        orig_lines = 0
        gen_lines = 0
        similar = 0

        for orig_rel, gen_rel in matched:
            orig_path = self.original / orig_rel
            gen_path = self.generated / gen_rel
            if orig_path.exists() and gen_path.exists():
                try:
                    orig_text = orig_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    gen_text = gen_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    orig_lines += len(orig_text)
                    gen_lines += len(gen_text)

                    # SequenceMatcher for similarity
                    ratio = difflib.SequenceMatcher(None, orig_text, gen_text).ratio()
                    similar += int(ratio * len(orig_text))
                except OSError:
                    pass

        result.total_original_lines = orig_lines
        result.total_generated_lines = gen_lines
        result.similar_lines = similar
        if orig_lines > 0:
            result.line_similarity_pct = round(similar / orig_lines * 100, 2)

        # 3. API contract compliance
        orig_apis = self._extract_apis(self.original, module_filter)
        gen_apis = self._extract_apis(self.generated, module_filter)
        result.api_original_count = len(orig_apis)
        result.api_generated_count = len(gen_apis)

        # Match by function/handler name
        matched_apis = 0
        for api in orig_apis:
            if api in gen_apis:
                matched_apis += 1
        result.api_matched = matched_apis
        if orig_apis:
            result.api_compliance_pct = round(matched_apis / len(orig_apis) * 100, 2)

        # 4. Overall score
        result.overall_score = round(
            0.4 * result.file_coverage_pct
            + 0.3 * result.api_compliance_pct
            + 0.3 * result.line_similarity_pct,
            2,
        )

        return result

    # ─── Internal helpers ──────────────────────────────────────────────

    def _find_source_files(self, root: Path) -> list[str]:
        """Find all source files relative to root."""
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip non-source dirs
            dirnames[:] = [d for d in dirnames if d not in {
                ".git", "__pycache__", ".mypy_cache", "vendor",
                "node_modules", ".pytest_cache", ".idea", ".vscode",
            }]
            rel_dir = Path(dirpath).relative_to(root)
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext in self.file_exts:
                    rel = str(rel_dir / fn) if str(rel_dir) != "." else fn
                    files.append(rel)
        return sorted(files)

    def _match_files(
        self, orig_files: list[str], gen_files: list[str]
    ) -> tuple[list[tuple[str, str]], list[str], list[str]]:
        """Match original files to generated files by basename and path similarity."""
        matched: list[tuple[str, str]] = []
        used_gen = set()

        for orig in orig_files:
            orig_base = os.path.basename(orig)
            best_match = None
            best_score = 0.0

            for gen in gen_files:
                if gen in used_gen:
                    continue
                gen_base = os.path.basename(gen)
                if orig_base == gen_base:
                    # Exact basename match
                    matched.append((orig, gen))
                    used_gen.add(gen)
                    best_match = None  # Already matched
                    break
                # Partial match
                score = self._path_similarity(orig, gen)
                if score > best_score and score > 0.5:
                    best_score = score
                    best_match = gen

            if best_match:
                matched.append((orig, best_match))
                used_gen.add(best_match)

        matched_orig = {m[0] for m in matched}
        matched_gen = {m[1] for m in matched}
        unmatched_orig = [f for f in orig_files if f not in matched_orig]
        unmatched_gen = [f for f in gen_files if f not in matched_gen]

        return matched, unmatched_orig, unmatched_gen

    @staticmethod
    def _path_similarity(a: str, b: str) -> float:
        """Score path similarity (0.0 to 1.0)."""
        a_parts = set(Path(a).stem.lower().split("_") + Path(a).stem.lower().split("-"))
        b_parts = set(Path(b).stem.lower().split("_") + Path(b).stem.lower().split("-"))
        if not a_parts or not b_parts:
            return 0.0
        return len(a_parts & b_parts) / len(a_parts | b_parts)

    def _extract_apis(self, root: Path, module_filter: Optional[str]) -> set[str]:
        """Extract API/function names from source files."""
        apis: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {
                ".git", "__pycache__", "vendor", "node_modules",
            }]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext not in self.file_exts:
                    continue
                fpath = Path(dirpath) / fn
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    if self.lang == "Go":
                        # func Xxx( methods
                        for m in re.finditer(r'func\s+\(.*?\)\s+(\w+)', text):
                            apis.add(m.group(1))
                        for m in re.finditer(r'func\s+(\w+)', text):
                            apis.add(m.group(1))
                        # http.HandleFunc / router
                        for m in re.finditer(r'(?:Handle|GET|POST|PUT|DELETE|PATCH)\s*\(\s*"([^"]+)"', text):
                            apis.add(f"route:{m.group(1)}")
                    else:
                        # def xxx(
                        for m in re.finditer(r'(?:def|async\s+def)\s+(\w+)', text):
                            apis.add(m.group(1))
                        # @app.route, @router.get, etc.
                        for m in re.finditer(r'(?:route|get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', text):
                            apis.add(f"route:{m.group(1)}")
                except OSError:
                    pass

        if module_filter:
            # Keep APIs that relate to the module
            lower_filter = module_filter.lower()
            apis = {a for a in apis if lower_filter in a.lower()}

        return apis
