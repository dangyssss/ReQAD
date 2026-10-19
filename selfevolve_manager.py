from __future__ import annotations
import ast
import tempfile
import sys
import os
import re
import shutil
import datetime
import textwrap
import selfevolve_rubric
import asyncio
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from metagpt.llm import LLM
import importlib


class SelfevolveRubricManager:
    def __init__(self, file_path="selfevolve_rubric.py"):
        self.file_path = os.path.join(CURRENT_DIR, file_path)
        self.backup_dir = os.path.join(CURRENT_DIR, "backups")
        self.base_backup_path = os.path.join(self.backup_dir, "SelfevolveRubric_BASE.py.bak")
        self.llm = LLM()
        
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

        if not os.path.exists(self.base_backup_path) and os.path.exists(self.file_path):
            shutil.copy2(self.file_path, self.base_backup_path)
            print(f"[SelfevolveRubricManager] Base snapshot (Initial Seed) created for safety.")

    def _commit(self, version: str):
        """
        Store the current SelfevolveRubric into the backup repository before executing physical modifications.
        """
        if os.path.exists(self.file_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"SelfevolveRubric_v{version}_{timestamp}.py.bak"
            backup_path = os.path.join(self.backup_dir, backup_name)
            shutil.copy2(self.file_path, backup_path)
            print(f"[SelfevolveRubricManager] Snapshot created: {backup_name}")

    async def rollback(self):
        """Restore backups in reverse chronological order."""
        backups = []

        for filename in os.listdir(self.backup_dir):
            match = re.fullmatch(
                r"SelfevolveRubric_v.+_(\d{8}_\d{6})\.py\.bak",
                filename
            )
            if match:
                backups.append((match.group(1), filename))

        backups.sort(key=lambda item: (item[0], item[1]))

        if not backups:
            print("[Rollback] No backups available.")
            return False

        cursor_path = os.path.join(
            self.backup_dir, ".rollback_cursor"
        )

        if os.path.exists(cursor_path):
            with open(cursor_path, "r", encoding="utf-8") as f:
                previous = f.read().strip()

            indices = [
                i for i, (_, name) in enumerate(backups)
                if name == previous
            ]

            if not indices:
                print("[Rollback] Previous backup not found.")
                return False

            index = indices[0] - 1
        else:
            index = len(backups) - 1

        if index < 0:
            print("[Rollback] No older backup available.")
            return False

        filename = backups[index][1]
        backup_path = os.path.join(self.backup_dir, filename)

        shutil.copy2(backup_path, self.file_path)
        importlib.reload(selfevolve_rubric)
        cursor_path = os.path.join(self.backup_dir, ".rollback_cursor")
        if os.path.exists(cursor_path):
            os.remove(cursor_path)
        with open(cursor_path, "w", encoding="utf-8") as f:
            f.write(filename)

        print(f"[Rollback] Restored: {filename}")
        return True

    async def reset_to_base(self):
        """
        Factory Reset: Bypass all intermediate versions and restore directly to the initial seed version.
        """
        if not os.path.exists(self.base_backup_path):
            print("[SelfevolveRubricManager] Critical Error: Base backup not found.")
            return False
        
        shutil.copy2(self.base_backup_path, self.file_path)
        importlib.reload(selfevolve_rubric)
        # A successful reset starts a new rollback sequence.
        cursor_path = os.path.join(self.backup_dir, ".rollback_cursor")
        if os.path.exists(cursor_path):
            os.remove(cursor_path)
        print(f"[FACTORY RESET] SelfevolveRubric has been restored to the INITIAL version (v1.0.0).")
        return True

    async def upgrade_rubric(self, user_feedback: str):
        """
        Incorporate user feedback to automatically rewrite and upgrade SelfevolveRubrical rules via LLM.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Cannot find {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            current_code = f.read()

        version_match = re.search(r'selfevolve_rubric_VERSION\s*=\s*"([^"]+)"',current_code)
        current_version = version_match.group(1) if version_match else "unknown"

        self._commit(current_version)

        # Validate the generated source before touching the rubric file.
        # The validator accepts changes only to literal rubric rules and version.
        def inspect_rubric_source(code: str):
            tree = ast.parse(code)
            permitted = {"selfevolve_rubric_VERSION", "selfevolve_rubric_RULES"}
            values = {}
            structure = []

            for node in tree.body:
                if (isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in permitted):
                    name = node.targets[0].id
                    if name in values:
                        raise ValueError(f"Duplicate rubric definition: {name}")
                    try:
                        values[name] = ast.literal_eval(node.value)
                    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
                        raise ValueError(f"Rubric definition is not a literal: {name}") from exc
                    structure.append(("rubric_definition", name))
                else:
                    # Reject altered imports, functions, or any added executable code.
                    structure.append(("unchanged", ast.dump(node, include_attributes=False)))

            if set(values) != permitted:
                missing = sorted(permitted - set(values))
                raise ValueError(f"Missing rubric definitions: {missing}")
            return values, structure

        def validate_rubric_update(original_code: str, candidate_code: str):
            original, original_structure = inspect_rubric_source(original_code)
            candidate, candidate_structure = inspect_rubric_source(candidate_code)

            if candidate_structure != original_structure:
                raise ValueError(
                    "Upgrade rejected: code outside the rubric rules and version was changed."
                )

            old_version = original["selfevolve_rubric_VERSION"]
            new_version = candidate["selfevolve_rubric_VERSION"]
            pattern = r"\d+\.\d+\.\d+"
            if (not isinstance(old_version, str)
                    or not isinstance(new_version, str)
                    or re.fullmatch(pattern, old_version) is None
                    or re.fullmatch(pattern, new_version) is None
                    or tuple(map(int, new_version.split(".")))
                    <= tuple(map(int, old_version.split(".")))):
                raise ValueError("Rubric version must be a strictly increasing X.Y.Z version.")

            old_rules = original["selfevolve_rubric_RULES"]
            new_rules = candidate["selfevolve_rubric_RULES"]
            if (not isinstance(old_rules, dict)
                    or not isinstance(new_rules, dict)
                    or set(new_rules) != set(old_rules)):
                raise ValueError("The original rubric categories must be preserved.")

            for category, articles in new_rules.items():
                if (not isinstance(articles, dict)
                        or not articles
                        or not all(isinstance(key, str) and key
                                   and isinstance(value, str) and value.strip()
                                   for key, value in articles.items())):
                    raise ValueError(f"Invalid rubric articles in category: {category}")

        prompt = textwrap.dedent(f"""
            You are a "Low-Level System Rules Architect". Your task is to modify the Audit SelfevolveRubric based on user feedback.
            
            [Current Code Content]:
            {current_code}
            
            [User Modification Intent / Feedback]:
            "{user_feedback}"
            
            ### Strict Rewriting Requirements:
            1. Modify only the articles within the selfevolve_rubric_RULES dictionary.
            2. Increment the version string in selfevolve_rubric_VERSION.
            3. Preserve the get_selfevolve_rubric_text function without modification.
            4. Output only the raw Python code content. Do not include Markdown code block fences (such as ```python).
            
            Please begin rewriting:
        """)

        print(f"[SelfevolveRubricManager] Automatically upgrading the SelfevolveRubric based on user feedback...")
        new_code = await self.llm.aask(prompt, stream=False)
        
        new_code = new_code.strip()
        fenced = re.fullmatch(
            r"```(?:python)?[ \t]*\n(.*?)\n```",
            new_code,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            new_code = fenced.group(1)

        # No file write or module reload occurs if validation fails.
        validate_rubric_update(current_code, new_code)

        # Write to a temporary file in the same directory, then replace atomically.
        # A failed write before os.replace leaves the original rubric untouched.
        def atomic_write(code: str):
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=os.path.dirname(self.file_path),
                    prefix=".rubric_",
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:
                    temp_path = temp_file.name
                    temp_file.write(code)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())

                os.replace(temp_path, self.file_path)
            finally:
                if temp_path is not None and os.path.exists(temp_path):
                    os.remove(temp_path)

        replaced = False
        try:
            atomic_write(new_code)
            replaced = True
            importlib.reload(selfevolve_rubric)
        except Exception as error:
            if replaced:
                # A reload failure can leave the module partly initialized.
                # Restore both the source file and its in-memory definitions.
                try:
                    atomic_write(current_code)
                    importlib.reload(selfevolve_rubric)
                except Exception as restore_error:
                    raise RuntimeError(
                        "Rubric upgrade failed and automatic restoration also failed. "
                        "Restore the original rubric from backups manually."
                    ) from restore_error

            raise RuntimeError(
                "Rubric upgrade failed. The previous rubric was preserved or restored."
            ) from error

        # A successful upgrade starts a new rollback sequence.
        cursor_path = os.path.join(self.backup_dir, ".rollback_cursor")
        if os.path.exists(cursor_path):
            os.remove(cursor_path)
        print(f"SelfevolveRubric successfully upgraded and saved to {self.file_path}")


if __name__ == "__main__":  
    async def init_manager():
        mgr = SelfevolveRubricManager()
        print("[SelfevolveRubricManager] Initialization complete")
        print(f"Backup directory status: {'Ready' if os.path.exists(mgr.backup_dir) else 'Failed'}")    
    asyncio.run(init_manager())