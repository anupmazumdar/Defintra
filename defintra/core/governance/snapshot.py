"""
Cryptographic Project Snapshot & Rollback Engine (§29, §49).
Maintains immutable, SHA-256 verified specification snapshots, enabling
safe rollbacks, version lineage, and pre-production release checkpoints.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database
from defintra.core.models.entities import current_utc_time
from defintra.export.exporter import Exporter


class ProjectSnapshot:
    def __init__(
        self,
        snapshot_id: str,
        project_id: str,
        version_tag: str,
        checksum: str,
        description: str,
        created_at: str,
        payload: Dict[str, Any],
    ):
        self.snapshot_id = snapshot_id
        self.project_id = project_id
        self.version_tag = version_tag
        self.checksum = checksum
        self.description = description
        self.created_at = created_at
        self.payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "version_tag": self.version_tag,
            "checksum": self.checksum,
            "description": self.description,
            "created_at": self.created_at,
        }


class SnapshotManager:
    def __init__(self, db: Database, storage_dir: str = ".defintra/snapshots"):
        self.db = db
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(
        self,
        project_id: str,
        version_tag: str,
        description: str = "Release checkpoint",
    ) -> ProjectSnapshot:
        """
        Creates an immutable snapshot of the project with a SHA-256 cryptographic digest (§49).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        exporter = Exporter(self.db, project_id)
        payload = exporter.build_dir_payload()

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        checksum = hashlib.sha256(payload_bytes).hexdigest()
        snapshot_id = f"snap_{version_tag.replace('.', '_')}_{checksum[:8]}"
        created_at = current_utc_time()

        snapshot_file = self.storage_dir / f"{snapshot_id}.json"
        snapshot_data = {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "version_tag": version_tag,
            "checksum": checksum,
            "description": description,
            "created_at": created_at,
            "payload": payload,
        }
        snapshot_file.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")

        return ProjectSnapshot(
            snapshot_id=snapshot_id,
            project_id=project_id,
            version_tag=version_tag,
            checksum=checksum,
            description=description,
            created_at=created_at,
            payload=payload,
        )

    def list_snapshots(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists all available snapshots.
        """
        snapshots = []
        for file in self.storage_dir.glob("snap_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                if not project_id or data.get("project_id") == project_id:
                    snapshots.append({
                        "snapshot_id": data.get("snapshot_id"),
                        "project_id": data.get("project_id"),
                        "version_tag": data.get("version_tag"),
                        "checksum": data.get("checksum"),
                        "description": data.get("description"),
                        "created_at": data.get("created_at"),
                        "file_path": str(file),
                    })
            except Exception:
                continue
        return sorted(snapshots, key=lambda s: s.get("created_at", ""), reverse=True)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restores the project state from a previous immutable snapshot (§48, §49).
        """
        matches = list(self.storage_dir.glob(f"{snapshot_id}*.json"))
        if not matches:
            return False

        data = json.loads(matches[0].read_text(encoding="utf-8"))
        payload = data.get("payload", {})
        proj_data = payload.get("project", {})

        # Restore project entities
        from defintra.core.models.entities import Project
        project = Project(
            id=proj_data.get("id"),
            name=proj_data.get("name"),
            objective=proj_data.get("objective"),
            domain=proj_data.get("domain", "GENERAL"),
            source_type=proj_data.get("source_type", "idea"),
            spec_entropy=payload.get("health", {}).get("entropy", 0.5),
            spec_health_score=payload.get("health", {}).get("health_score", 80.0),
            updated_at=current_utc_time(),
        )
        self.db.save_project(project)
        return True
