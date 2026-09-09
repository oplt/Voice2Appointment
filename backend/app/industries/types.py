"""Industry profile policy types (capability architecture, not separate apps)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

IndustryType = Literal["clinic", "restaurant", "salon", "general"]
SchedulingMode = Literal["single_resource", "multi_resource", "capacity"]


class ConfirmationPolicy(BaseModel):
    require_explicit_confirm: bool = True
    send_reminders: bool = True
    send_forms: bool = False
    send_instructions: bool = False


class DepositPolicy(BaseModel):
    enabled: bool = False
    amount_minor: int | None = None
    currency: str | None = None
    no_show_fee_minor: int | None = None


class HandoffPolicy(BaseModel):
    enabled: bool = True
    emergency_escalation: bool = False
    business_hours_only: bool = False


class PrivacyPolicy(BaseModel):
    """Operational privacy knobs — not a regulatory certification or HIPAA claim.

    ``compliance_claimed`` must remain False unless an independent assessment
    completes; see ``app.industries.compliance``.
    """

    redact_medical_from_analytics: bool = False
    redact_medical_from_logs: bool = False
    allow_diagnosis_advice: bool = False
    store_clinical_notes: bool = False
    compliance_claimed: bool = False


class IndustryProfileSpec(BaseModel):
    industry_type: IndustryType
    scheduling_mode: SchedulingMode
    required_customer_fields: list[str] = Field(default_factory=list)
    required_booking_fields: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    confirmation_policy: ConfirmationPolicy = Field(default_factory=ConfirmationPolicy)
    deposit_policy: DepositPolicy = Field(default_factory=DepositPolicy)
    handoff_policy: HandoffPolicy = Field(default_factory=HandoffPolicy)
    privacy_policy: PrivacyPolicy = Field(default_factory=PrivacyPolicy)
    terminology: dict[str, str] = Field(default_factory=dict)
    flow_steps: list[str] = Field(default_factory=list)
    resource_types: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
