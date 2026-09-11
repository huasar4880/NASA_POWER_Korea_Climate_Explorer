"""해안거리 분석의 provenance gate.

이번 저장소에는 라이선스와 해상도가 확인된 대한민국 coastline geometry가 포함되어
있지 않다. 도시명·행정구역을 이용한 임의 분류를 피하기 위해 Stage-12에서는 해안/내륙
수치분석을 명시적으로 보류한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoastalAvailability:
    """해안거리 분석 실행 가능성과 보류 근거."""

    available: bool
    source: str
    license: str
    reason: str


def assess_coastline_availability() -> CoastalAvailability:
    """검증된 local coastline geometry가 없음을 안전하게 보고한다."""

    return CoastalAvailability(
        available=False,
        source=(
            "candidate: Korea Hydrographic and Oceanographic Agency, National Coastline "
            "2025 SHP (data.go.kr dataset 15083948); geometry not bundled"
        ),
        license="public data portal: no restriction on scope of use",
        reason=(
            "coastal classification deferred: the official source and license were identified, "
            "but no reviewed local geometry/CRS is bundled; distance and threshold results are "
            "not generated until acquisition, checksum, CRS, and geometry validity are reproducible"
        ),
    )
