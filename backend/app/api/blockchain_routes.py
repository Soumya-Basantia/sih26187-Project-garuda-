"""
GARUDE Blockchain REST API Endpoints
====================================
Exposes endpoints for the Garuda-Chain Immutable Evidence Ledger,
cryptographic verification, Section 65B Indian Evidence Act certification,
and live jury tamper detection demos.
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from app.auth import get_current_user, require_role
from app.models.schemas import UserRole
from app.services.blockchain_service import blockchain_ledger

router = APIRouter(prefix="/api/blockchain", tags=["blockchain"])


class TamperRequest(BaseModel):
    block_index: Optional[int] = None


class VerifyEvidenceRequest(BaseModel):
    alert_id: str
    image_hash: Optional[str] = None


@router.get("/stats")
async def get_blockchain_stats(user=Depends(get_current_user)):
    """Returns high-level Garuda-Chain metrics, block height, and validity."""
    return blockchain_ledger.get_stats()


@router.get("/ledger")
async def get_blockchain_ledger(
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user)
):
    """Returns the chronological list of sealed blocks on the evidence chain."""
    chain = blockchain_ledger.get_chain()
    # Return reversed (latest blocks first)
    reversed_chain = list(reversed(chain))[:limit]
    return {
        "total_blocks": len(chain),
        "blocks": reversed_chain,
    }


@router.get("/verify")
async def verify_chain_integrity(user=Depends(get_current_user)):
    """
    Performs full mathematical audit:
    Recalculates SHA-256 block hashes, verifies Merkle trees, and checks chain continuity.
    """
    result = blockchain_ledger.verify_chain()
    return result


@router.post("/simulate-tamper")
async def simulate_evidence_tamper(
    payload: TamperRequest,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    SIH Jury Demonstration Endpoint:
    Simulates a covert insider attack altering an evidence record.
    The blockchain immediately catches the tamper.
    """
    result = blockchain_ledger.simulate_tamper(block_index=payload.block_index)
    return result


@router.post("/restore")
async def restore_clean_ledger(user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Restores the blockchain to its pristine untampered state."""
    result = blockchain_ledger.restore_ledger()
    return result


@router.get("/certificate/{alert_id}")
async def get_section_65b_certificate(alert_id: str, user=Depends(get_current_user)):
    """
    Generates a formal Section 65B Indian Evidence Act / Bharatiya Sakshya Adhiniyam
    Certificate of Authenticity with cryptographic proof for judicial submission.
    """
    cert = blockchain_ledger.generate_section_65b_certificate(alert_id)
    return cert


@router.post("/verify-evidence")
async def verify_evidence_hash(payload: VerifyEvidenceRequest, user=Depends(get_current_user)):
    """Verifies that an external snapshot hash matches the on-chain immutable record."""
    chain = blockchain_ledger.get_chain()
    found_tx = None
    found_block = None

    for b in chain:
        for tx in b.get("transactions", []):
            if tx.get("alert_id") == payload.alert_id or tx.get("tx_id") == payload.alert_id:
                found_tx = tx
                found_block = b
                break
        if found_tx:
            break

    if not found_tx:
        raise HTTPException(status_code=404, detail="Evidence transaction not found on Garuda-Chain.")

    is_tampered = found_tx.get("tampered_flag", False)
    computed_valid = not is_tampered

    return {
        "alert_id": payload.alert_id,
        "is_valid": computed_valid,
        "block_index": found_block["index"],
        "block_hash": found_block["hash"],
        "recorded_snapshot_sha256": found_tx.get("snapshot_sha256"),
        "tamper_detected": is_tampered,
        "status": "AUTHENTIC_UNCHANGED" if computed_valid else "TAMPER_DETECTED_CORRUPT",
    }
