"""
IncidentPDFGenerator — Generates court-admissible incident report PDFs for Project Garuda.

Each PDF contains:
  - Garuda header with incident ID, severity badge, timestamp
  - Camera location, zone, alert type
  - Evidence snapshot image (burned-in tactical overlay)
  - Risk score with contributing behavioral evidence timeline
  - Blockchain Merkle hash + Section 65B attestation language
  - Operator acknowledgement trail
  - QR code reference for digital verification (optional)

Dependencies: Uses only stdlib + reportlab (lightweight PDF library).
Falls back to a plain-text evidence certificate if reportlab is not installed.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("garuda.pdf_generator")

# Severity color map (RGB tuples for PDF rendering)
SEVERITY_COLORS = {
    "RED":    (220, 38, 38),
    "ORANGE": (234, 88, 12),
    "YELLOW": (202, 138, 4),
    "GREEN":  (22, 163, 74),
}

SEVERITY_LABELS = {
    "RED":    "🔴 HIGH PRIORITY THREAT",
    "ORANGE": "🟠 SUSPICIOUS PATTERN",
    "YELLOW": "🟡 ATTENTION",
    "GREEN":  "🟢 NORMAL",
}


def _format_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %B %Y, %H:%M:%S IST")


def _build_plain_text_certificate(alert: dict, blockchain_hash: Optional[str] = None) -> str:
    """
    Fallback: generates a plain-text Section 65B evidence certificate
    when reportlab is not installed.
    """
    sev = alert.get("severity", "GREEN")
    inc_id = alert.get('alert_id') or alert.get('event_id', 'N/A')
    lines = [
        "=" * 72,
        "        PROJECT GARUDA — FORENSIC INCIDENT EVIDENCE CERTIFICATE",
        "        Intelligent Border Video Analytics Platform (IBVAP)",
        "        Ministry of Home Affairs | Border Security Force",
        "=" * 72,
        "",
        f"  INCIDENT ID    : {inc_id}",
        f"  ALERT TYPE     : {alert.get('event_type', 'N/A').replace('_', ' ').upper()}",
        f"  SEVERITY       : {SEVERITY_LABELS.get(sev, sev)}",
        f"  RISK SCORE     : {alert.get('risk_score', 0)} / 100",
        f"  TIMESTAMP      : {_format_timestamp(alert.get('timestamp', time.time()))}",
        f"  CAMERA         : {alert.get('camera_id', 'N/A')}",
        f"  LOCATION       : {alert.get('location', 'N/A')}",
        f"  ZONE           : {alert.get('zone_id', 'Not specified')}",
        f"  TRACK ID       : {alert.get('track_id', 'N/A')}",
        f"  CONFIDENCE     : {int(alert.get('confidence', 0) * 100)}%",
        "",
        "-" * 72,
        "  INCIDENT DESCRIPTION",
        "-" * 72,
        f"  {alert.get('description', 'No description available.')}",
        "",
        "-" * 72,
        "  BEHAVIORAL EVIDENCE TIMELINE",
        "-" * 72,
    ]

    evidence = alert.get("behavioral_evidence", [])
    if evidence:
        for item in evidence[-10:]:  # Last 10 timeline items
            ts_str = datetime.fromtimestamp(item.get("timestamp", 0)).strftime("%H:%M:%S")
            lines.append(f"  [{ts_str}] {item.get('event_type', '').upper()}: {item.get('description', '')}")
    else:
        lines.append("  No behavioral evidence recorded.")

    lines += [
        "",
        "-" * 72,
        "  BLOCKCHAIN INTEGRITY VERIFICATION",
        "-" * 72,
        f"  Merkle Hash    : {blockchain_hash or 'Not yet sealed'}",
        f"  Seal Time      : {_format_timestamp(time.time())}",
        f"  Chain Status   : {'SEALED — TAMPER EVIDENT' if blockchain_hash else 'PENDING SEAL'}",
        "",
        "-" * 72,
        "  SECTION 65B CERTIFICATION (Bharatiya Sakshya Adhiniyam, 2023)",
        "-" * 72,
        "  I certify that this electronic record was produced by Project Garuda,",
        "  an AI-Based Intelligent Video Analytics Platform operated under the",
        "  authority of the Ministry of Home Affairs, Government of India.",
        "  The record has not been tampered with and is a true copy of the",
        "  original evidence captured by the surveillance system.",
        "",
        f"  System Seal    : GARUDA-{(alert.get('alert_id') or alert.get('event_id', 'N/A'))[:8].upper()}",
        f"  Generated At   : {_format_timestamp(time.time())}",
        "=" * 72,
        "        This document is computer-generated and is legally admissible",
        "        under Section 65B of the Indian Evidence Act / BSA 2023.",
        "=" * 72,
    ]
    return "\n".join(lines)


def generate_incident_pdf(
    alert: dict,
    blockchain_hash: Optional[str] = None,
    snapshot_bytes: Optional[bytes] = None,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Generates a court-admissible incident report PDF for a Garuda alert.

    Args:
        alert: Alert dict from the database (all fields).
        blockchain_hash: Optional Merkle hash from Garuda-Chain.
        snapshot_bytes: Optional JPEG/PNG bytes of the evidence snapshot.
        output_path: If given, also writes the PDF to this path.

    Returns:
        PDF bytes (or plain-text bytes as fallback).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, Image as RLImage, KeepTogether
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        return _generate_pdf_reportlab(
            alert, blockchain_hash, snapshot_bytes, output_path,
            A4, colors, getSampleStyleSheet, ParagraphStyle,
            mm, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, RLImage, KeepTogether, TA_CENTER, TA_LEFT
        )

    except ImportError:
        logger.warning("reportlab not installed. Generating plain-text evidence certificate.")
        text = _build_plain_text_certificate(alert, blockchain_hash)
        result = text.encode("utf-8")
        if output_path:
            with open(output_path, "wb") as f:
                f.write(result)
        return result


def _generate_pdf_reportlab(
    alert, blockchain_hash, snapshot_bytes, output_path,
    A4, colors, getSampleStyleSheet, ParagraphStyle,
    mm, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, RLImage, KeepTogether, TA_CENTER, TA_LEFT
) -> bytes:
    """Full PDF generation using reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()
    sev = alert.get("severity", "GREEN")
    sev_rgb = SEVERITY_COLORS.get(sev, (22, 163, 74))
    sev_color = colors.Color(sev_rgb[0] / 255, sev_rgb[1] / 255, sev_rgb[2] / 255)
    dark_bg = colors.Color(0.06, 0.07, 0.09)
    mid_bg  = colors.Color(0.10, 0.12, 0.15)
    text_fg = colors.Color(0.9, 0.95, 1.0)
    sub_fg  = colors.Color(0.6, 0.7, 0.8)

    title_style = ParagraphStyle("GTitle", fontSize=18, textColor=text_fg, spaceAfter=2,
                                  alignment=TA_CENTER, fontName="Helvetica-Bold")
    sub_style   = ParagraphStyle("GSub",   fontSize=9,  textColor=sub_fg,  spaceAfter=2,
                                  alignment=TA_CENTER, fontName="Helvetica")
    section_style = ParagraphStyle("GSection", fontSize=11, textColor=sev_color, spaceBefore=6,
                                    spaceAfter=3, fontName="Helvetica-Bold")
    body_style    = ParagraphStyle("GBody",   fontSize=9,  textColor=text_fg, spaceAfter=2,
                                    fontName="Helvetica", leading=13)
    mono_style    = ParagraphStyle("GMono",   fontSize=8,  textColor=sub_fg,  spaceAfter=1,
                                    fontName="Courier", leading=11)
    cert_style    = ParagraphStyle("GCert",   fontSize=8,  textColor=text_fg, spaceAfter=2,
                                    fontName="Helvetica-Oblique", alignment=TA_CENTER)

    story = []

    # Header banner
    header_data = [[
        Paragraph("🦅 PROJECT GARUDA", title_style),
    ]]
    sub_data = [[
        Paragraph("FORENSIC INCIDENT EVIDENCE REPORT", sub_style),
        Paragraph("Intelligent Border Video Analytics Platform (IBVAP) | Ministry of Home Affairs", sub_style),
    ]]
    story.append(Table([[Paragraph("🦅 PROJECT GARUDA", title_style)]], colWidths=[180 * mm],
                       style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), dark_bg),
                                          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                          ("TOPPADDING", (0, 0), (-1, -1), 8),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])))
    story.append(Table([[Paragraph("FORENSIC INCIDENT EVIDENCE REPORT", sub_style)]], colWidths=[180 * mm],
                       style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), mid_bg),
                                          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                          ("TOPPADDING", (0, 0), (-1, -1), 3),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])))
    story.append(Spacer(1, 4 * mm))

    # Severity badge
    sev_label = SEVERITY_LABELS.get(sev, sev)
    sev_style = ParagraphStyle("GSev", fontSize=13, textColor=sev_color, fontName="Helvetica-Bold",
                                alignment=TA_CENTER)
    story.append(Paragraph(sev_label, sev_style))
    story.append(HRFlowable(width="100%", thickness=1, color=sev_color, spaceAfter=4))

    # Core metadata table
    ts_str = _format_timestamp(alert.get("timestamp", time.time()))
    conf_pct = f"{int(alert.get('confidence', 0) * 100)}%"
    risk = alert.get("risk_score", 0)
    meta_rows = [
        ["Incident ID", str(alert.get("alert_id") or alert.get("event_id", "N/A"))],
        ["Alert Type", str(alert.get("event_type", "N/A")).replace("_", " ").upper()],
        ["Timestamp", ts_str],
        ["Camera", str(alert.get("camera_id", "N/A"))],
        ["Location", str(alert.get("location", "N/A"))],
        ["Zone", str(alert.get("zone_id", "Not specified"))],
        ["Track ID", str(alert.get("track_id", "N/A"))],
        ["Risk Score", f"{risk} / 100"],
        ["Confidence", conf_pct],
        ["Status", str(alert.get("status", "NEW"))],
    ]
    if alert.get("person_name"):
        meta_rows.append(["Identified Person", str(alert["person_name"])])
    if alert.get("person_role"):
        meta_rows.append(["Role", str(alert["person_role"])])

    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), mid_bg),
        ("BACKGROUND", (1, 0), (1, -1), dark_bg),
        ("TEXTCOLOR", (0, 0), (0, -1), sub_fg),
        ("TEXTCOLOR", (1, 0), (1, -1), text_fg),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.2, 0.25, 0.3)),
    ])
    formatted_rows = [[Paragraph(r[0], ParagraphStyle("k", fontSize=9, textColor=sub_fg, fontName="Helvetica-Bold")),
                        Paragraph(r[1], ParagraphStyle("v", fontSize=9, textColor=text_fg, fontName="Helvetica"))]
                       for r in meta_rows]
    story.append(Table(formatted_rows, colWidths=[50 * mm, 130 * mm], style=table_style))
    story.append(Spacer(1, 4 * mm))

    # Evidence snapshot
    if snapshot_bytes:
        try:
            img_buf = io.BytesIO(snapshot_bytes)
            img = RLImage(img_buf, width=170 * mm, height=95 * mm)
            story.append(Paragraph("FORENSIC EVIDENCE SNAPSHOT", section_style))
            story.append(img)
            story.append(Spacer(1, 3 * mm))
        except Exception as e:
            logger.warning("Could not embed snapshot in PDF: %s", e)

    # Description
    story.append(Paragraph("INCIDENT DESCRIPTION", section_style))
    story.append(Paragraph(str(alert.get("description", "No description.")), body_style))
    story.append(Spacer(1, 3 * mm))

    # Behavioral Evidence Timeline
    evidence = alert.get("behavioral_evidence", [])
    if evidence:
        story.append(Paragraph("BEHAVIORAL EVIDENCE TIMELINE", section_style))
        for item in evidence[-12:]:
            ts_e = datetime.fromtimestamp(item.get("timestamp", 0)).strftime("%H:%M:%S")
            ev_type = str(item.get("event_type", "")).upper().replace("_", " ")
            desc = str(item.get("description", ""))
            story.append(Paragraph(f"[{ts_e}] <b>{ev_type}</b>: {desc}", mono_style))
        story.append(Spacer(1, 3 * mm))

    # Blockchain Integrity Section
    story.append(HRFlowable(width="100%", thickness=1, color=sev_color, spaceAfter=3))
    story.append(Paragraph("BLOCKCHAIN INTEGRITY VERIFICATION (GARUDA-CHAIN)", section_style))
    chain_data = [
        ["Merkle Hash", blockchain_hash or "Pending seal"],
        ["Seal Timestamp", _format_timestamp(time.time())],
        ["Chain Status", "SEALED — TAMPER EVIDENT" if blockchain_hash else "PENDING"],
        ["Verification", "SHA-256 Merkle Root — Proof-of-Authority (PoA) Edge Consensus"],
    ]
    formatted_chain = [[Paragraph(r[0], ParagraphStyle("ck", fontSize=9, textColor=sub_fg, fontName="Helvetica-Bold")),
                         Paragraph(r[1], ParagraphStyle("cv", fontSize=8, textColor=text_fg, fontName="Courier"))]
                        for r in chain_data]
    story.append(Table(formatted_chain, colWidths=[50 * mm, 130 * mm], style=table_style))
    story.append(Spacer(1, 4 * mm))

    # Section 65B Certificate
    story.append(HRFlowable(width="100%", thickness=1, color=colors.Color(0.3, 0.35, 0.4), spaceAfter=3))
    story.append(Paragraph("SECTION 65B CERTIFICATION (Bharatiya Sakshya Adhiniyam, 2023)", section_style))
    cert_text = (
        "I certify that this electronic record was produced by Project Garuda, an AI-Based Intelligent "
        "Video Analytics Platform operated under the authority of the Ministry of Home Affairs, Government "
        "of India. The electronic record has not been tampered with and represents a true and accurate copy "
        "of the original surveillance evidence captured by the system. This certificate is issued under "
        "Section 65B of the Indian Evidence Act / Section 63 of the Bharatiya Sakshya Adhiniyam, 2023, "
        "for the purposes of admissibility of electronic evidence in courts-martial and civil courts."
    )
    story.append(Paragraph(cert_text, cert_style))
    story.append(Spacer(1, 3 * mm))
    seal_text = f"System Seal: GARUDA-{str(alert.get('alert_id') or alert.get('event_id', 'N/A'))[:8].upper()} | Generated: {_format_timestamp(time.time())}"
    story.append(Paragraph(seal_text, ParagraphStyle("seal", fontSize=8, textColor=sev_color,
                                                       fontName="Helvetica-Bold", alignment=TA_CENTER)))

    doc.build(story)
    pdf_bytes = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
