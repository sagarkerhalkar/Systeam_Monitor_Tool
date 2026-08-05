from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence
import hashlib
import re
import uuid

INVALID_VALUES = {
    "", "none", "null", "unknown", "unknown-host", "unknown host", "n/a", "na", "-",
    "default string", "system serial number", "baseboard serial number",
    "to be filled by o.e.m.", "not specified", "not available",
}

TOKEN_FIELDS = (
    "system_uuid",
    "motherboard_serial",
    "bios_serial",
    "chassis_serial",
    "disk_serial",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _valid(value: object) -> str:
    value = _clean(value)
    if value in INVALID_VALUES:
        return ""
    token = re.sub(r"[^a-z0-9]", "", value)
    if len(token) < 6:
        return ""
    if set(token) <= {"0", "f"}:
        return ""
    return value


def _canonical_key(seed: str) -> str:
    return "client:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class IdentityRecord:
    row_id: str
    hostname: str = ""
    agent_install_id: str = ""
    persistent_client_id: str = ""
    system_uuid: str = ""
    motherboard_serial: str = ""
    bios_serial: str = ""
    chassis_serial: str = ""
    disk_serial: str = ""
    updated_at: str = ""
    os_family: str = ""
    invalid: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "IdentityRecord":
        hostname = _clean(data.get("hostname") or data.get("hostname_key"))
        row_id = str(
            data.get("row_id") or data.get("machine_id") or data.get("machine_key") or ""
        ).strip()
        return cls(
            row_id=row_id,
            hostname=hostname,
            agent_install_id=_valid(data.get("agent_install_id")),
            persistent_client_id=_valid(data.get("persistent_client_id")),
            system_uuid=_valid(data.get("system_uuid") or data.get("system_uuid_key")),
            motherboard_serial=_valid(
                data.get("motherboard_serial") or data.get("motherboard_serial_key")
            ),
            bios_serial=_valid(data.get("bios_serial") or data.get("bios_serial_key")),
            chassis_serial=_valid(
                data.get("chassis_serial") or data.get("chassis_serial_key")
            ),
            disk_serial=_valid(data.get("disk_serial") or data.get("disk_serial_key")),
            updated_at=str(data.get("updated_at") or ""),
            os_family=str(data.get("os_family") or ""),
            invalid=bool(data.get("invalid"))
            or hostname in {"", "unknown", "unknown-host", "unknown host"},
        )

    def permanent_id(self) -> str:
        return self.agent_install_id or self.persistent_client_id

    def stable_tokens(self) -> set[tuple[str, str]]:
        return {
            (field_name, getattr(self, field_name))
            for field_name in TOKEN_FIELDS
            if getattr(self, field_name)
        }


@dataclass
class IdentityResolution:
    canonical_by_row: dict[str, str]
    source_by_row: dict[str, str]
    excluded_rows: set[str] = field(default_factory=set)
    groups: dict[str, list[str]] = field(default_factory=dict)
    quarantined_tokens: set[tuple[str, str]] = field(default_factory=set)

    @property
    def physical_client_count(self) -> int:
        return len(self.groups)


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        values = list(values)
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def resolve_identities(records: Sequence[IdentityRecord]) -> IdentityResolution:
    """Resolve current-state rows into physical clients conservatively.

    Rules:
    1. Exclude explicit invalid/unknown rows.
    2. Permanent agent installation ID is the only unconditional merge key.
    3. Legacy rows merge only when hostname is identical and at least one stable
       hardware identifier agrees.
    4. A hardware identifier shared across different hostnames is quarantined.
    5. Hostname, IP, MAC and motherboard serial alone are never global merge keys.
    """
    active = [record for record in records if record.row_id and not record.invalid]
    excluded = {record.row_id for record in records if record.row_id and record.invalid}
    uf = _UnionFind(record.row_id for record in active)

    by_permanent: dict[str, list[IdentityRecord]] = defaultdict(list)
    token_hostnames: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_hostname: dict[str, list[IdentityRecord]] = defaultdict(list)

    for record in active:
        if record.permanent_id():
            by_permanent[record.permanent_id()].append(record)
        if record.hostname:
            by_hostname[record.hostname].append(record)
        for token in record.stable_tokens():
            if record.hostname:
                token_hostnames[token].add(record.hostname)

    quarantined = {
        token for token, hostnames in token_hostnames.items() if len(hostnames) > 1
    }

    for members in by_permanent.values():
        anchor = members[0].row_id
        for member in members[1:]:
            uf.union(anchor, member.row_id)

    for members in by_hostname.values():
        if len(members) < 2:
            continue
        for index, left in enumerate(members):
            left_tokens = left.stable_tokens() - quarantined
            if not left_tokens:
                continue
            for right in members[index + 1 :]:
                if left_tokens.intersection(right.stable_tokens() - quarantined):
                    uf.union(left.row_id, right.row_id)

    members_by_root: dict[str, list[IdentityRecord]] = defaultdict(list)
    for record in active:
        members_by_root[uf.find(record.row_id)].append(record)

    canonical_by_row: dict[str, str] = {}
    source_by_row: dict[str, str] = {}
    groups: dict[str, list[str]] = {}

    for members in members_by_root.values():
        permanent_ids = sorted({m.permanent_id() for m in members if m.permanent_id()})
        if permanent_ids:
            seed = "agent:" + permanent_ids[0]
            source = "agent_install_id"
        else:
            row_seed = sorted(m.row_id for m in members)[0]
            seed = "legacy:" + row_seed
            source = "legacy_conservative"
        canonical = _canonical_key(seed)
        row_ids = sorted(m.row_id for m in members)
        groups[canonical] = row_ids
        for row_id in row_ids:
            canonical_by_row[row_id] = canonical
            source_by_row[row_id] = source

    return IdentityResolution(
        canonical_by_row=canonical_by_row,
        source_by_row=source_by_row,
        excluded_rows=excluded,
        groups=groups,
        quarantined_tokens=quarantined,
    )


def new_agent_install_id() -> str:
    """Generate a non-hostname permanent agent installation identifier."""
    return str(uuid.uuid4())
