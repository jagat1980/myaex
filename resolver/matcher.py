"""5-tier identity matching engine enforcing ontology match rules."""

import uuid
from typing import Any
from connectors.common.models import NormalisedRecord
from resolver.models import MatchConfidence, MatchKeyType, ResolutionResult


class EntityMatcher:
    """Evaluates candidate records against known CI aliases and attributes."""

    @staticmethod
    def normalize_name(name: str | None) -> str | None:
        """Normalize hostname or FQDN to lowercase stripped format."""
        if not name:
            return None
        cleaned = name.strip().lower()
        return cleaned if cleaned else None

    def match(
        self,
        record: NormalisedRecord,
        existing_aliases: dict[str, uuid.UUID],  # key: "<source_system>:<source_id>" -> ci_id
        known_cis: dict[uuid.UUID, dict[str, Any]],  # key: ci_id -> attributes
    ) -> ResolutionResult:
        """Resolve a record against known CIs using the 5-tier key hierarchy."""
        alias_key = f"{record.source_system}:{record.source_id}"

        # 0. Fast-path: Already linked directly in ci_alias
        if alias_key in existing_aliases:
            existing_ci_id = existing_aliases[alias_key]
            known_props = known_cis.get(existing_ci_id, {})
            # Keep confidence or bump if cloud baseline
            conf = 1.00 if record.source_system == "azure" else float(known_props.get("confidence", 0.90))
            return ResolutionResult(
                ci_id=existing_ci_id,
                confidence=conf,
                matched_key_type=MatchKeyType.CLOUD_ID if record.source_system == "azure" else MatchKeyType.HOSTNAME,
                matched_key_value=record.source_id,
                is_new=False,
            )

        norm_fqdn = self.normalize_name(record.fqdn)
        norm_hostname = self.normalize_name(record.name)
        ip = record.ip.strip() if record.ip else None
        cloud_id = record.cloud_id.strip() if record.cloud_id else None

        # Tier 1: Cloud ID / Azure Resource ID (Confidence 1.00)
        if cloud_id:
            for cand_id, cand in known_cis.items():
                cand_cloud_id = cand.get("cloud_id")
                if cand_cloud_id and cand_cloud_id.lower() == cloud_id.lower():
                    return ResolutionResult(
                        ci_id=cand_id,
                        confidence=MatchConfidence.CLOUD_ID,
                        matched_key_type=MatchKeyType.CLOUD_ID,
                        matched_key_value=cloud_id,
                        is_new=False,
                    )

        # Tier 2: CMDB sys_id referenced by another source (Confidence 0.95)
        sys_id = record.attributes.get("sys_id")
        if sys_id:
            for cand_id, cand in known_cis.items():
                if cand.get("sys_id") == sys_id:
                    return ResolutionResult(
                        ci_id=cand_id,
                        confidence=MatchConfidence.SYS_ID,
                        matched_key_type=MatchKeyType.SYS_ID,
                        matched_key_value=str(sys_id),
                        is_new=False,
                    )

        # Tier 3: Normalized FQDN (Confidence 0.90)
        if norm_fqdn:
            for cand_id, cand in known_cis.items():
                cand_fqdn = self.normalize_name(cand.get("fqdn"))
                if cand_fqdn and cand_fqdn == norm_fqdn:
                    return ResolutionResult(
                        ci_id=cand_id,
                        confidence=MatchConfidence.FQDN,
                        matched_key_type=MatchKeyType.FQDN,
                        matched_key_value=norm_fqdn,
                        is_new=False,
                    )

        # Tier 4: Hostname + Validated IP Address (Confidence 0.80)
        if norm_hostname and ip:
            for cand_id, cand in known_cis.items():
                cand_name = self.normalize_name(cand.get("name"))
                cand_ip = cand.get("ip")
                cand_all_ips = cand.get("all_ips") or []
                ip_match = (cand_ip == ip) or (ip in cand_all_ips)
                if cand_name == norm_hostname and ip_match:
                    return ResolutionResult(
                        ci_id=cand_id,
                        confidence=MatchConfidence.HOSTNAME_IP,
                        matched_key_type=MatchKeyType.HOSTNAME_IP,
                        matched_key_value=f"{norm_hostname}:{ip}",
                        is_new=False,
                    )

        # Tier 5: Hostname Only (Confidence 0.60, with conflict checking)
        if norm_hostname:
            matched_candidates: list[tuple[uuid.UUID, dict[str, Any]]] = []
            for cand_id, cand in known_cis.items():
                cand_name = self.normalize_name(cand.get("name"))
                if cand_name == norm_hostname:
                    matched_candidates.append((cand_id, cand))

            if len(matched_candidates) == 1:
                cand_id, cand = matched_candidates[0]
                cand_ip = cand.get("ip")
                # Conflict Check: Both have IP addresses specified, but they differ
                if ip and cand_ip and ip != cand_ip:
                    # Isolated candidate - conflict detected
                    new_id = self._generate_canonical_id(record)
                    return ResolutionResult(
                        ci_id=new_id,
                        confidence=MatchConfidence.HOSTNAME,
                        matched_key_type=MatchKeyType.HOSTNAME,
                        matched_key_value=norm_hostname,
                        is_new=True,
                        is_conflict=True,
                        conflict_reason=(
                            f"Ambiguous match on hostname '{norm_hostname}': "
                            f"conflicting IP addresses (incoming={ip}, existing={cand_ip})"
                        ),
                    )

                return ResolutionResult(
                    ci_id=cand_id,
                    confidence=MatchConfidence.HOSTNAME,
                    matched_key_type=MatchKeyType.HOSTNAME,
                    matched_key_value=norm_hostname,
                    is_new=False,
                )
            elif len(matched_candidates) > 1:
                # Multiple candidates match same hostname -> Ambiguity conflict
                new_id = self._generate_canonical_id(record)
                return ResolutionResult(
                    ci_id=new_id,
                    confidence=MatchConfidence.HOSTNAME,
                    matched_key_type=MatchKeyType.HOSTNAME,
                    matched_key_value=norm_hostname,
                    is_new=True,
                    is_conflict=True,
                    conflict_reason=(
                        f"Ambiguous match: multiple existing CIs ({len(matched_candidates)}) "
                        f"share hostname '{norm_hostname}'"
                    ),
                )

        # No Match Found: Assign a new canonical UUID
        new_id = self._generate_canonical_id(record)
        conf = 1.00 if record.source_system == "azure" else 0.90
        return ResolutionResult(
            ci_id=new_id,
            confidence=conf,
            matched_key_type=None,
            matched_key_value=None,
            is_new=True,
        )

    @staticmethod
    def _generate_canonical_id(record: NormalisedRecord) -> uuid.UUID:
        """Derive a deterministic UUID for a new CI."""
        # If cloud_id or source_id is already a valid UUID, reuse it
        if record.cloud_id:
            try:
                return uuid.UUID(record.cloud_id)
            except (ValueError, AttributeError):
                pass

        # Otherwise create deterministic namespace UUID
        namespace_seed = f"{record.tenant_id}:{record.source_system}:{record.source_id}"
        return uuid.uuid5(uuid.NAMESPACE_DNS, namespace_seed)
