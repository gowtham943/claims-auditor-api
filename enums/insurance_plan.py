from enum import Enum


class Geography(str, Enum):
    INDIA = "INDIA"
    WESTERN = "WESTERN"


class PlanType(str, Enum):
    CMCHIS = "CMCHIS"
    NHIS = "NHIS"
    HMO = "HMO"
    PPO = "PPO"


PLAN_TYPES_BY_GEOGRAPHY: dict[Geography, set[PlanType]] = {
    Geography.INDIA: {PlanType.CMCHIS, PlanType.NHIS},
    Geography.WESTERN: {PlanType.HMO, PlanType.PPO},
}

PLAN_TYPE_LABELS: dict[PlanType, str] = {
    PlanType.CMCHIS: "Chief Minister's Comprehensive Health Insurance Scheme",
    PlanType.NHIS: "New Health Insurance Scheme",
    PlanType.HMO: "Health Maintenance Organization",
    PlanType.PPO: "Preferred Provider Organization",
}


def validate_geography_and_plan(geography: str, plan_type: str) -> tuple[Geography, PlanType]:
    try:
        geo = Geography(geography.upper())
    except ValueError as exc:
        valid = ", ".join(g.value for g in Geography)
        raise ValueError(f"Invalid geography '{geography}'. Allowed: {valid}.") from exc

    try:
        plan = PlanType(plan_type.upper())
    except ValueError as exc:
        valid = ", ".join(p.value for p in PlanType)
        raise ValueError(f"Invalid plan type '{plan_type}'. Allowed: {valid}.") from exc

    if plan not in PLAN_TYPES_BY_GEOGRAPHY[geo]:
        allowed = ", ".join(p.value for p in PLAN_TYPES_BY_GEOGRAPHY[geo])
        raise ValueError(
            f"Plan type '{plan.value}' is not valid for geography '{geo.value}'. "
            f"Allowed for {geo.value}: {allowed}."
        )

    return geo, plan
