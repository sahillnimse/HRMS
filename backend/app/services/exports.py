"""Phase 3 exports: one-page executive candidate PDF (reportlab) and shortlist XLSX (openpyxl)."""

from io import BytesIO
from typing import Any, Dict, Iterable, List
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.user import UserRole
from app.schemas.candidate import CandidateResponse
from app.services.audit import blind_candidate_label, redact_ctc_for_role, redact_for_blind_screening


def _safe_p(text_val: Any, max_len: int = 450) -> str:
    raw = str(text_val or "").strip()
    if len(raw) > max_len:
        raw = raw[: max_len - 1].rstrip() + "…"
    return escape(raw)


def build_candidate_pdf(
    candidate: CandidateResponse,
    *,
    role: UserRole,
    blind: bool = False,
) -> bytes:
    """
    Generate a clean, single-page executive candidate PDF dossier.
    Respects viewer CTC redaction AND optional blind-screening anonymization.
    """
    data = redact_ctc_for_role(candidate, role)
    if blind:
        data = redact_for_blind_screening(data)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title=f"Candidate Profile - {data.full_name}",
    )

    styles = getSampleStyleSheet()
    indigo = colors.HexColor("#4F46E5")
    slate_900 = colors.HexColor("#0F172A")
    slate_600 = colors.HexColor("#475569")
    slate_200 = colors.HexColor("#E2E8F0")
    indigo_tint = colors.HexColor("#EEF2FF")

    title_style = ParagraphStyle(
        "CandTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=slate_900,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "CandSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=slate_600,
        spaceAfter=6,
    )
    sec_style = ParagraphStyle(
        "SecHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=indigo,
        spaceBefore=7,
        spaceAfter=3,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=slate_900,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=slate_600,
    )

    story: list[Any] = []

    # Header
    header_badge = "BLIND SCREENING BRIEF" if blind else "CANDIDATE DOSSIER"
    story.append(
        Paragraph(
            f'<font color="#4F46E5"><b>{header_badge}</b></font>  ·  HRMS AI',
            ParagraphStyle("Eyebrow", parent=small_style, fontSize=7.5, spaceAfter=3),
        )
    )
    story.append(Paragraph(_safe_p(data.full_name, 120), title_style))

    meta_parts = [
        data.primary_domain,
        f"{data.years_experience:.1f} yrs experience",
    ]
    if data.city:
        meta_parts.append(data.city)
    if not blind:
        if data.email:
            meta_parts.append(data.email)
        if data.phone:
            meta_parts.append(data.phone)
    story.append(Paragraph(_safe_p("  |  ".join(meta_parts), 260), sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=slate_200, spaceAfter=6))

    # Key facts strip (notice, relocation, source, optional CTC for admin/recruiter)
    facts: list[tuple[str, str]] = [
        ("Notice Period", f"{data.notice_period_days} days" if data.notice_period_days is not None else "—"),
        (
            "Relocation",
            "Open" if data.open_to_relocate is True else ("No" if data.open_to_relocate is False else "—"),
        ),
        ("Source", (data.source or "upload").title()),
    ]
    if role in (UserRole.admin, UserRole.recruiter):
        curr_txt = (
            f"{data.ctc_currency or 'INR'} {data.current_ctc:,.0f}"
            if data.current_ctc is not None
            else "—"
        )
        exp_txt = (
            f"{data.ctc_currency or 'INR'} {data.expected_ctc:,.0f}"
            if data.expected_ctc is not None
            else "—"
        )
        facts.append(("Current / Expected CTC", f"{curr_txt} / {exp_txt}"))

    fact_cells = [
        [Paragraph(f'<font color="#64748B" size="7"><b>{escape(k.upper())}</b></font><br/>{_safe_p(v, 50)}', body_style) for k, v in facts]
    ]
    col_w = (letter[0] - 1.1 * inch) / len(facts)
    tbl = Table(fact_cells, colWidths=[col_w] * len(facts))
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), indigo_tint),
                ("BOX", (0, 0), (-1, -1), 0.5, slate_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, slate_200),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl)

    # Executive Summary
    story.append(Paragraph("EXECUTIVE SUMMARY", sec_style))
    story.append(Paragraph(_safe_p(data.profile_summary, 480), body_style))

    # Skills & Tools
    if data.technical_skills or data.tools:
        story.append(Paragraph("SKILLS & TOOLS", sec_style))
        if data.technical_skills:
            story.append(
                Paragraph(
                    f"<b>Technical:</b> {_safe_p(', '.join(data.technical_skills[:18]), 260)}",
                    body_style,
                )
            )
        if data.tools:
            story.append(
                Paragraph(
                    f"<b>Tools & Platforms:</b> {_safe_p(', '.join(data.tools[:14]), 220)}",
                    small_style,
                )
            )

    # Work Experience (compact, max 4 roles, max 2 bullets each to keep single-page guarantee)
    if data.work_experience:
        story.append(Paragraph("EXPERIENCE", sec_style))
        for item in (data.work_experience or [])[:4]:
            if not isinstance(item, dict):
                continue
            title = item.get("job_title") or "Role"
            company = item.get("company") or ""
            dates = f"{item.get('start_date') or ''} – {item.get('end_date') or 'Present'}".strip(" –")
            line = f"<b>{_safe_p(title, 80)}</b>"
            if company:
                line += f"  ·  {_safe_p(company, 80)}"
            if dates:
                line += f'  <font color="#64748B">({escape(dates)})</font>'
            story.append(Paragraph(line, body_style))
            bullets = item.get("bullets") or []
            for b in bullets[:2]:
                if isinstance(b, str) and b.strip():
                    story.append(Paragraph(f"• {_safe_p(b, 175)}", small_style))
            story.append(Spacer(1, 3))

    # Education
    if data.education:
        story.append(Paragraph("EDUCATION", sec_style))
        for ed in (data.education or [])[:3]:
            if not isinstance(ed, dict):
                continue
            deg = ed.get("degree") or "Degree"
            inst = "[Institution Redacted]" if blind else (ed.get("institution") or "")
            yr = ed.get("graduation_year")
            edu_line = f"<b>{_safe_p(deg, 90)}</b>"
            if inst:
                edu_line += f" — {_safe_p(inst, 90)}"
            if yr:
                edu_line += f" ({yr})"
            story.append(Paragraph(edu_line, body_style))

    # Certifications / Languages
    extras: list[str] = []
    if data.certifications:
        extras.append(f"<b>Certifications:</b> {_safe_p(', '.join(data.certifications[:5]), 180)}")
    if data.languages:
        extras.append(f"<b>Languages:</b> {_safe_p(', '.join(data.languages[:6]), 120)}")
    if extras:
        story.append(Paragraph("CREDENTIALS", sec_style))
        for ex in extras:
            story.append(Paragraph(ex, small_style))

    doc.build(story)
    return buf.getvalue()


def build_shortlist_xlsx(
    rows: Iterable[Dict[str, Any]],
    *,
    sheet_title: str = "Shortlist",
    include_ctc: bool = True,
    include_job_columns: bool = False,
    blind: bool = False,
) -> bytes:
    """
    Build a formatted XLSX shortlist spreadsheet using openpyxl.
    Respects `include_ctc` (False for viewer) and `blind` (redacts name/email/phone/college).
    """
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = (sheet_title or "Shortlist")[:31]

    headers: List[str] = ["Candidate"]
    if not blind:
        headers.extend(["Email", "Phone"])
    headers.extend(["Domain", "Years Experience", "City"])
    if include_job_columns:
        headers.extend(["Stage", "Match Score", "Match Explanation"])
    headers.extend(["Technical Skills", "Tools"])
    if not blind:
        headers.append("Education")
    else:
        headers.append("Degree")
    headers.extend(["Notice Period (Days)", "Open to Relocate", "Source"])
    if include_ctc:
        headers.extend(["Current CTC", "Expected CTC", "Currency"])

    ws.append(headers)

    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", horizontal="left")

    for r in rows:
        cid = r.get("id", "")
        display_name = blind_candidate_label(cid) if blind else (r.get("full_name") or "")
        edu_items = r.get("education") or []
        if blind:
            edu_str = "; ".join(
                str(e.get("degree") or "") for e in edu_items if isinstance(e, dict) and e.get("degree")
            )
        else:
            edu_str = "; ".join(
                f"{e.get('degree') or ''} ({e.get('institution') or ''})".strip()
                for e in edu_items
                if isinstance(e, dict)
            )

        line: List[Any] = [display_name]
        if not blind:
            line.extend([r.get("email") or "", r.get("phone") or ""])
        line.extend(
            [
                r.get("primary_domain") or "",
                r.get("years_experience", 0.0),
                r.get("city") or "",
            ]
        )
        if include_job_columns:
            line.extend(
                [
                    r.get("stage") or "",
                    r.get("match_score") if r.get("match_score") is not None else "",
                    r.get("match_explanation") or "",
                ]
            )
        line.extend(
            [
                ", ".join(r.get("technical_skills") or []),
                ", ".join(r.get("tools") or []),
                edu_str,
                r.get("notice_period_days") if r.get("notice_period_days") is not None else "",
                "Yes" if r.get("open_to_relocate") is True else ("No" if r.get("open_to_relocate") is False else ""),
                r.get("source") or "upload",
            ]
        )
        if include_ctc:
            line.extend(
                [
                    r.get("current_ctc") if r.get("current_ctc") is not None else "",
                    r.get("expected_ctc") if r.get("expected_ctc") is not None else "",
                    r.get("ctc_currency") or "",
                ]
            )
        ws.append(line)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Auto-fit column widths within sensible bounds
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        max_len = max(
            (len(str(ws.cell(row=row_idx, column=col_idx).value or "")) for row_idx in range(1, ws.max_row + 1)),
            default=10,
        )
        ws.column_dimensions[col_letter].width = min(48, max(12, max_len + 3))

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_shortlist_pack_pdf(
    entries: List[Dict[str, Any]],
    *,
    job_title: str,
    department: str = "",
    location: str = "",
    role: UserRole,
    blind: bool = False,
) -> bytes:
    """
    Phase 4.5: Shortlist Pack PDF — strictly ONE page per candidate containing:
      - Candidate header (anonymized in blind mode; CTC omitted unless admin/recruiter)
      - Candidate Brief (<=5-line summary, strengths, 0-4 worth-verifying items)
      - Career Timeline Summary (tenure stats, recent roles, gap/overlap summary)
      - Top Skills & Tools
      - JD Match Explanation & Skill-Gap view
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title=f"Shortlist Pack - {job_title}",
    )

    styles = getSampleStyleSheet()
    teal = colors.HexColor("#0D8274")
    slate_900 = colors.HexColor("#0F172A")
    slate_600 = colors.HexColor("#475569")
    slate_200 = colors.HexColor("#E2E8F0")
    teal_tint = colors.HexColor("#EDFAF7")
    amber_tint = colors.HexColor("#FFFBEB")

    eyebrow_style = ParagraphStyle(
        "PackEyebrow",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=teal,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "PackTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=slate_900,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "PackSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=slate_600,
        spaceAfter=5,
    )
    sec_style = ParagraphStyle(
        "PackSec",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11.5,
        textColor=teal,
        spaceBefore=6,
        spaceAfter=2.5,
    )
    body_style = ParagraphStyle(
        "PackBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=11,
        textColor=slate_900,
    )
    small_style = ParagraphStyle(
        "PackSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10,
        textColor=slate_600,
    )

    story: list[Any] = []
    if not entries:
        story.append(Paragraph(f"SHORTLIST PACK · {_safe_p(job_title, 100)}", eyebrow_style))
        story.append(Paragraph("No candidates selected for this shortlist pack.", body_style))
        doc.build(story)
        return buf.getvalue()

    job_meta = " · ".join(p for p in (job_title, department, location) if p)

    for idx, entry in enumerate(entries):
        if idx > 0:
            story.append(PageBreak())

        cand_raw: CandidateResponse = entry["candidate"]
        cand = redact_ctc_for_role(cand_raw, role)
        if blind:
            cand = redact_for_blind_screening(cand)

        brief = entry.get("brief")
        timeline = entry.get("timeline")
        match = entry.get("match")

        badge_prefix = "BLIND SHORTLIST PACK" if blind else "SHORTLIST PACK"
        story.append(
            Paragraph(
                f"{badge_prefix} · {_safe_p(job_meta, 110)} · Candidate {idx + 1} of {len(entries)}",
                eyebrow_style,
            )
        )
        story.append(Paragraph(_safe_p(cand.full_name, 110), title_style))

        meta_parts = [cand.primary_domain, f"{cand.years_experience:.1f} yrs"]
        if cand.city:
            meta_parts.append(cand.city)
        if not blind:
            if cand.email:
                meta_parts.append(cand.email)
            if cand.phone:
                meta_parts.append(cand.phone)
        story.append(Paragraph(_safe_p("  |  ".join(meta_parts), 240), sub_style))
        story.append(HRFlowable(width="100%", thickness=0.8, color=slate_200, spaceAfter=5))

        # Key facts strip (CTC included ONLY for admin/recruiter)
        facts: list[tuple[str, str]] = [
            ("Match Score", f"{match['score']:.1f} / 100" if match else "Not scored"),
            ("Stage", str(entry.get("stage") or "Unassigned").title()),
            (
                "Notice",
                f"{cand.notice_period_days} days" if cand.notice_period_days is not None else "—",
            ),
        ]
        if role in (UserRole.admin, UserRole.recruiter):
            curr = (
                f"{cand.ctc_currency or 'INR'} {cand.current_ctc:,.0f}"
                if cand.current_ctc is not None
                else "—"
            )
            exp = (
                f"{cand.ctc_currency or 'INR'} {cand.expected_ctc:,.0f}"
                if cand.expected_ctc is not None
                else "—"
            )
            facts.append(("Current / Expected CTC", f"{curr} / {exp}"))

        col_w = (letter[0] - 1.1 * inch) / len(facts)
        fact_cells = [
            [
                Paragraph(
                    f'<font color="#64748B" size="6.8"><b>{escape(k.upper())}</b></font><br/>{_safe_p(v, 45)}',
                    body_style,
                )
                for k, v in facts
            ]
        ]
        tbl = Table(fact_cells, colWidths=[col_w] * len(facts))
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), teal_tint),
                    ("BOX", (0, 0), (-1, -1), 0.5, slate_200),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, slate_200),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tbl)

        # 1. Candidate Brief
        story.append(Paragraph("CANDIDATE BRIEF", sec_style))
        if brief:
            brief_lines = [ln.strip() for ln in str(brief.summary).splitlines() if ln.strip()][:5]
            story.append(Paragraph(_safe_p(" ".join(brief_lines), 420), body_style))
            if brief.strengths:
                story.append(Spacer(1, 3))
                for st in list(brief.strengths)[:3]:
                    story.append(Paragraph(f"• <b>Strength:</b> {_safe_p(st, 150)}", small_style))
            if brief.verify_items:
                story.append(Spacer(1, 3))
                v_lines = [
                    f"[{v.severity.upper()}] {_safe_p(v.message, 150)}"
                    for v in list(brief.verify_items)[:3]
                ]
                v_tbl = Table(
                    [
                        [
                            Paragraph(
                                '<b>Worth Verifying (informational only):</b><br/>'
                                + "<br/>".join(f"• {ln}" for ln in v_lines),
                                small_style,
                            )
                        ]
                    ],
                    colWidths=[letter[0] - 1.1 * inch],
                )
                v_tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), amber_tint),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FDE68A")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.append(v_tbl)
        else:
            story.append(Paragraph(_safe_p(cand.profile_summary, 360), body_style))

        # 2. Match Explanation & Skill-Gap
        if match:
            bd = match.get("breakdown") or {}
            story.append(Paragraph("JOB FIT & SKILL-GAP SUMMARY", sec_style))
            why = bd.get("why") or match.get("explanation") or ""
            if why:
                story.append(Paragraph(_safe_p(why, 240), body_style))
            matched_req = bd.get("matched_required_skills") or []
            missing_req = bd.get("missing_required_skills") or []
            adj = bd.get("adjacent_skills") or []
            gap_bits: list[str] = []
            if matched_req:
                gap_bits.append(f"<b>Matched:</b> {_safe_p(', '.join(matched_req[:8]), 130)}")
            if missing_req:
                gap_bits.append(f"<b>Missing:</b> {_safe_p(', '.join(missing_req[:6]), 110)}")
            if adj:
                adj_txt = ", ".join(
                    f"{a.get('candidate_skill')} → {a.get('required_skill')}" for a in adj[:3]
                )
                gap_bits.append(f"<b>Adjacent:</b> {_safe_p(adj_txt, 120)}")
            if gap_bits:
                story.append(Paragraph("  ·  ".join(gap_bits), small_style))

        # 3. Career Timeline Summary
        story.append(Paragraph("CAREER TIMELINE SUMMARY", sec_style))
        if timeline:
            ts = timeline.tenure_stats
            t_summary = (
                f"<b>{ts.total_years:.1f} yrs</b> computed across <b>{ts.role_count}</b> roles "
                f"· Avg tenure: <b>{ts.average_tenure_months:.0f} mos</b> "
                f"· Jobs (last 5 yrs): <b>{ts.jobs_last_5_years}</b>"
            )
            if timeline.gaps:
                t_summary += f" · Gaps (&gt;{timeline.gap_threshold_months}m): {len(timeline.gaps)}"
            if timeline.overlaps:
                t_summary += f" · Overlaps: {len(timeline.overlaps)}"
            story.append(Paragraph(t_summary, small_style))
            for r in list(timeline.roles)[:4]:
                dates = f"{r.start_ym or r.raw_start or '?'} – {r.end_ym or r.raw_end or '?'}"
                dur = f" ({r.duration_months}m)" if r.duration_months else ""
                story.append(
                    Paragraph(
                        f"• <b>{_safe_p(r.job_title, 70)}</b> at {_safe_p(r.company, 65)} "
                        f'<font color="#64748B">[{escape(dates)}{dur}]</font>',
                        small_style,
                    )
                )

        # 4. Top Skills & Education (compact)
        story.append(Paragraph("TOP SKILLS & CREDENTIALS", sec_style))
        if cand.technical_skills:
            story.append(
                Paragraph(
                    f"<b>Technical:</b> {_safe_p(', '.join(cand.technical_skills[:14]), 220)}",
                    small_style,
                )
            )
        if cand.tools:
            story.append(
                Paragraph(
                    f"<b>Tools:</b> {_safe_p(', '.join(cand.tools[:10]), 180)}",
                    small_style,
                )
            )
        if cand.education:
            edu_bits = []
            for ed in (cand.education or [])[:2]:
                if isinstance(ed, dict):
                    deg = ed.get("degree") or "Degree"
                    inst = "[Institution Redacted]" if blind else (ed.get("institution") or "")
                    edu_bits.append(f"{deg} ({inst})" if inst else str(deg))
            if edu_bits:
                story.append(Paragraph(f"<b>Education:</b> {_safe_p('; '.join(edu_bits), 180)}", small_style))

    doc.build(story)
    return buf.getvalue()
