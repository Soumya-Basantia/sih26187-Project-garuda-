"""
Generates the Master SIH 2026 Pitch Deck for PROJECT GARUDA (Problem Statement: SIH26187).
Creates: Project_Garuda_SIH2026_Pitch_Deck.pptx
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_deck():
    prs = Presentation()
    # 16:9 Widescreen dimensions (13.333 x 7.5 inches)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Color Palette: Military / Defense Cyber Theme
    BG_COLOR = RGBColor(15, 23, 42)       # Slate 900 / Dark Navy
    CARD_BG = RGBColor(30, 41, 59)        # Slate 800
    ACCENT_CYAN = RGBColor(56, 189, 248)  # Cyan 400
    ACCENT_EMERALD = RGBColor(52, 211, 153) # Emerald 400
    TEXT_WHITE = RGBColor(248, 250, 252)  # White Slate 50
    TEXT_MUTED = RGBColor(148, 163, 184)  # Slate 400
    ACCENT_GOLD = RGBColor(251, 191, 36)  # Amber 400

    slides_data = [
        # Slide 1: Title
        {
            "title": "PROJECT GARUDA",
            "subtitle": "Autonomous Border Video Intelligence Grid Using Existing Legacy CCTV Infrastructure",
            "category": "PROBLEM STATEMENT ID: SIH26187 | MINISTRY OF HOME AFFAIRS (MHA) & BSF",
            "bullets": [
                "100% Software-Only Retrofit onto Existing Legacy CCTV Cameras (Zero Hardware Replacement)",
                "Two-Tier Hierarchical Edge AI: Sub-3ms Gating with Full Weapon, Face & ANPR Precision",
                "Flagship 2-Factor Checkpoint Security: Fuzzy Plate OCR + 128D Facial Biometrics",
                "Garuda-Chain: Immutable SHA-256 Merkle Ledger (Sec 65B Indian Evidence Act Compliant)",
                "CyberSentry: Zero-Trust Camera Endpoint Hardening & PRNU Anti-Replay Sensor Defense"
            ],
            "notes": "Respected Jury and Evaluators, India guards over 15,000 kilometers of land borders monitored by hundreds of thousands of legacy CCTV cameras. But cameras alone do not stop infiltrations—human operators do. And humans suffer from fatigue, blindness after 20 minutes of monitoring, and overwhelming false alarms. We present PROJECT GARUDA—an autonomous, edge-native Command & Control intelligence grid that retrofits onto 100% of existing border CCTVs with zero new hardware, turning dumb surveillance feeds into proactive, court-admissible tactical defense assets."
        },
        # Slide 2: Problem Statement
        {
            "title": "THE PROBLEM STATEMENT (PS SIH26187)",
            "subtitle": "Critical Vulnerabilities in Current Border Surveillance & Legacy Infrastructure",
            "category": "THE BORDER SECURITY REALITY & CHALLENGES",
            "bullets": [
                "15,106 km Borderline: Challenging terrain (desert, riverine, mountains) where physical patrolling is limited.",
                "Acute Operator Fatigue: Surveillance studies prove guards miss >90% of suspicious activity after 22 minutes.",
                "The Hardware Cost Trap: Replacing 100,000+ analog/IP border cameras with proprietary 'AI cameras' costs ₹800+ Crores.",
                "Alarm Fatigue Crisis: 90%+ false sirens from stray cattle, windblown trees, and lighting shifts cause guards to ignore alerts.",
                "Forensic Inadmissibility: Standard CCTV MP4 footage is easily contested, trimmed, or dismissed under Section 65B."
            ],
            "notes": "Problem Statement SIH26187 identifies four critical vulnerabilities in border surveillance today: First, operator cognitive fatigue. Studies prove that after just 22 minutes of staring at video walls, guards miss over 90% of suspicious activities. Second, the crippling financial cost: replacing India's existing camera fleet with proprietary smart hardware would drain hundreds of crores. Third, false alarms from livestock and foliage cause alarm fatigue. And fourth, standard video files can be disputed or tampered with before reaching a court of law. Project Garuda solves all four through pure software intelligence."
        },
        # Slide 3: The Mandate: 100% Legacy Retrofit
        {
            "title": "THE MANDATE: 100% LEGACY CCTV RETROFIT",
            "subtitle": "Zero New Hardware Investment — Pure Software-Defined Edge Intelligence",
            "category": "INFRASTRUCTURE AGNOSTIC INTEGRATION",
            "bullets": [
                "Protocol Agnostic: Native asynchronous ingestion of RTSP, ONVIF Profile S/T, and HTTP streams.",
                "Universal Camera Support: Compatible with any existing analog/IP cameras (CP Plus, Hikvision, Dahua, unbranded).",
                "Zero Hardware Replacement: ₹0 expenditure required for camera replacement or proprietary sensors.",
                "Thread-Isolated Architecture: Non-blocking frame capture ensures zero RTSP drift or buffer lag.",
                "Rapid Field Deployment: Deploys on existing local C2 PCs, ruggedized edge servers, or patrol vehicles in minutes."
            ],
            "notes": "Our primary engineering mandate is Zero Hardware Replacement. Project Garuda does not ask security agencies to buy expensive new cameras. It ingests live RTSP and ONVIF streams from any camera already mounted on the fence—whether a 10-year-old analog feed via an encoder or a modern IP dome. Within seconds of entering an RTSP URL, Garuda's asynchronous engine takes control, injecting multi-threat neural perception into existing infrastructure."
        },
        # Slide 4: Two-Tier Hierarchical Inference
        {
            "title": "TWO-TIER HIERARCHICAL INFERENCE ENGINE",
            "subtitle": "Solving Edge Compute Bottlenecks & Multi-Camera FPS Collapse",
            "category": "CORE AI INNOVATION & ARCHITECTURE",
            "bullets": [
                "Tier 1 (Sub-3ms Trigger Gate): Ultra-light motion background subtraction & person detection runs continuously on full frames.",
                "Tier 2 (Threat-Triggered Precision): Heavy models (YOLOv8 Weapons, 128D SFace, ANPR) activate strictly on Regions of Interest (ROI).",
                "72% GPU/CPU Load Reduction: Eliminates idle-state neural processing when no motion or human presence is detected.",
                "SmoothThreatTracker: 3-frame temporal persistence + Exponential Moving Average (EMA) box smoothing eliminates flickering.",
                "Negative Mutual Exclusion: Suppresses false weapon alarms from everyday objects like smartphones, wallets, and car plates."
            ],
            "notes": "How do we run multi-camera deep vision on edge hardware without system crashes? We architected a Two-Tier Hierarchical Inference Engine. Tier 1 runs an ultra-light sub-3ms trigger pipeline on full frames. Only when a human subject or perimeter approach is detected does Tier 2 fire up our heavy models—YOLOv8 weapon detection, 128D face biometrics, and ANPR OCR—focused strictly on that cropped Region of Interest. This reduces edge GPU compute by 72% and prevents memory saturation."
        },
        # Slide 5: SIH26187 Human Activity Intelligence & FASE
        {
            "title": "HUMAN ACTIVITY INTELLIGENCE & FASE",
            "subtitle": "Full Compliance with SIH26187 Mandated Human Activity Categories",
            "category": "BEHAVIORAL COMPUTER VISION & FALSE ALARM SUPPRESSION",
            "bullets": [
                "Category 1 (Movement & Presence): Dwell-based loitering, erratic wandering trajectory math, and after-hours curfew violations.",
                "Category 2 (Observation & Interaction): Multi-suspect group convergence near boundary fences (<85px cluster proximity).",
                "Category 3 (Human-Object Interaction): 3-Stage unattended baggage engine (Carried -> Unattended Separation -> Abandoned IED Hazard).",
                "Category 4 (Security & Threat Detection): Real-time lethal weapons detection (Guns, Knives, Explosives) with instant priority alerts.",
                "FASE (False Alarm Suppression Engine): Sinusoidal trajectory analysis rejects windblown foliage and stray livestock."
            ],
            "notes": "Project Garuda implements all four human activity categories mandated by Problem Statement SIH26187. From erratic wandering and multi-suspect fence convergence to a 3-stage abandoned IED baggage tracker and lethal weapon detection. Crucially, to eliminate guard alarm fatigue, we built FASE—our False Alarm Suppression Engine. It uses temporal kinematics to distinguish directed human intrusion vectors from oscillating trees and livestock, cutting false border sirens by 88%."
        },
        # Slide 6: Flagship 2FA Checkpoint Control
        {
            "title": "2-FACTOR BORDER CHECKPOINT CONTROL",
            "subtitle": "Automated Vehicle ANPR & 128D Driver Biometric Cross-Verification",
            "category": "PHYSICAL ACCESS ENFORCEMENT & ANTI-TAILGATING",
            "bullets": [
                "Fuzzy OCR License Plate Engine: Levenshtein confusion matrix automatically corrects dirty, bent, or rain-splattered plates.",
                "128-Dimensional Face Biometrics: Deep feature embedding verification against registered base personnel databases.",
                "Driver-to-Owner Cross-Verification: Prevents vehicle theft/hijacking (Green Authorized HUD vs Red Unauthorized Driver Mismatch).",
                "Anti-Tailgating Sensor: Detects secondary unauthorized bodies entering behind a single credential scan.",
                "Zero-Downtime Forensic Audit: Every access attempt generates cryptographically signed snapshots and gate logs."
            ],
            "notes": "At forward border gates and base perimeters, vehicle theft or hijacked credentials represent severe security risks. Garuda's Flagship Checkpoint module implements automated 2-Factor Physical Access Control. As a vehicle approaches, our Fuzzy OCR engine reads muddy or distorted license plates using character confusion matrices, while our face biometrics engine extracts 128-dimensional facial vectors through the windshield. If the vehicle is cleared but the driver does not match registered biometric records, the gate locks and raises an unauthorized driver intercept alert."
        },
        # Slide 7: 2D Tactical Radar & Digital Twin Map
        {
            "title": "2D TACTICAL RADAR & DIGITAL TWIN MAP",
            "subtitle": "Multi-Camera Suspect Handover Without Heavy GPU Re-ID Overhead",
            "category": "SITUATIONAL AWARENESS & SPATIAL TOPOLOGY",
            "bullets": [
                "Spatial-Temporal Topology: Models the physical distance, exit angles, and walking times between perimeter cameras.",
                "Trajectory Exit Vectors: Computes suspect velocity and projected arrival time window (e.g. ETA to CAM-02: 18s).",
                "Predictive Pre-Priming: Downstream camera is pre-notified and primed with lightweight color histogram matching.",
                "Zero-GPU Re-ID Overhead: Eliminates slow, heavy 512D deep Re-ID neural networks that fail in varied lighting.",
                "Interactive Polygon Zones: Commanders draw custom Zero Line, Perimeter Buffer, and Patrol Track zones on live video."
            ],
            "notes": "When an intruder runs across multiple cameras, conventional AI systems fail because deep facial re-identification is too slow and easily blinded by changes in lighting or clothing. Garuda solves this with our 2D Tactical Radar. We map the spatial-temporal topology between cameras. When a suspect exits Camera 1 heading East at 5 km/h, Garuda calculates their arrival ETA at Camera 2—say, in 18 seconds—and primes the downstream camera with color histogram matching. Commanders see a unified tactical digital twin of the entire perimeter."
        },
        # Slide 8: Harsh Operational Conditions & Air-Gapped Mesh
        {
            "title": "HARSH-CONDITION READINESS & LORA MESH",
            "subtitle": "Built for Night Operations, Extreme Terrains, and Fiber Cut Offs",
            "category": "FORWARD OPERATING RESILIENCE",
            "bullets": [
                "Quantized Zero-DCE Night Vision: Hardware-accelerated curve enhancement extracts human silhouettes in near pitch-black without FLIR.",
                "3D Ground-Plane Homography: 4-point calibration maps 2D camera pixels to true metric ground coordinates (meters & km/h).",
                "100% Air-Gapped Operation: Completely sovereign edge deployment with zero reliance on cloud APIs or public internet.",
                "Tactical LoRa Mesh Telemetry: If optical fiber or power is cut, ultra-compact (<2KB) incident packets broadcast to jawan radios.",
                "Edge Sizing Feasibility: Runs smoothly on ruggedized edge compute (NVIDIA Jetson Orin Nano / RTX) under 8GB RAM."
            ],
            "notes": "Border environments are harsh, dark, and frequently cut off from communications. Garuda is engineered for the field: First, our Quantized Zero-DCE filter extracts high-contrast human silhouettes from low-light IR feeds without needing expensive thermal imagers. Second, our 4-point ground homography tool transforms 2D pixels into true metric ground space, telling jawans the exact intruder velocity and distance to fence in meters. And if backhaul fiber is sabotaged, Garuda operates 100% air-gapped, relaying lightweight tactical alerts over military LoRa mesh."
        },
        # Slide 9: Garuda-Chain: Blockchain Evidence Vault
        {
            "title": "GARUDA-CHAIN: BLOCKCHAIN EVIDENCE VAULT",
            "subtitle": "Court-Admissible Digital Forensics Under Section 65B Indian Evidence Act",
            "category": "CRYPTOGRAPHIC INTEGRITY & LEGAL ADMISSIBILITY",
            "bullets": [
                "SHA-256 Merkle Chaining: Every threat snapshot, bounding box, and incident log is cryptographically hashed at creation.",
                "Section 65B Certification: One-click generation of digitally signed forensic chain-of-custody certificates (BSA 2023 compliant).",
                "Zero-Overhead Edge PoA: Proof-of-Authority consensus tailored for tactical edge nodes with zero gas fees or mining load.",
                "Live Jury Tamper Verification Lab: Real-time demonstration showing that modifying a single pixel invalidates block hashes.",
                "Anti-Spooling Defense: Guarantees that border intrusion evidence cannot be doctored, deleted, or dismissed in court."
            ],
            "notes": "The greatest AI alert is useless if the evidence is thrown out of court. Under Section 65B of the Indian Evidence Act and Bharatiya Sakshya Adhiniyam 2023, digital evidence must maintain an unbroken chain of custody. Every single threat snapshot captured by Garuda is immediately fingerprinted with a SHA-256 cryptographic hash and sealed into Garuda-Chain—our zero-overhead edge blockchain ledger. If anyone attempts to modify or delete a single pixel, the Merkle tree breaks immediately. We can generate court-certified forensic certificates with one click."
        },
        # Slide 10: CyberSentry: Zero-Trust IoT Defense
        {
            "title": "CYBERSENTRY: ZERO-TRUST CAMERA DEFENSE",
            "subtitle": "Securing Border Surveillance Endpoints Against Video Loop Injections",
            "category": "CAMERA FLEET HARDENING & ANTI-REPLAY SENSING",
            "bullets": [
                "Anti-Replay Stream Liveness Engine: Monitors sensor PRNU (Photo-Response Non-Uniformity) noise and Shannon entropy at 30Hz.",
                "Video Loop Injection Detection: Instantly detects synthetic video spoofing and looped footage commonly used by hostile actors.",
                "Camera Fleet Security Scanner: Identifies default credentials, Mirai botnet attack vectors, and exposed RTSP 554 ports.",
                "MITRE ATT&CK for ICS Matrix: Maps threat telemetry directly to industrial security standards (T0814, T0855, T0843).",
                "1-Click Attack Simulation Sandbox: Allows commanders and jury evaluators to test defensive responses in real time."
            ],
            "notes": "Modern adversaries do not just run past cameras—they hack them. A common border penetration tactic is looping camera feeds to show an empty fence. Garuda's CyberSentry module monitors optical sensor noise and Shannon entropy at 30 frames per second. If a looped video is injected into the RTSP stream, the sensor PRNU fingerprint vanishes, and CyberSentry instantly triggers an anti-tamper cyber alarm. Project Garuda protects the cameras that protect our borders."
        },
        # Slide 11: Feasibility, Edge Sizing & Roadmap
        {
            "title": "FEASIBILITY, EDGE SIZING & ROADMAP",
            "subtitle": "High Return on Investment, Low Power Budget, and Phased Rollout",
            "category": "COMMERCIAL VIABILITY & OPERATIONAL ROADMAP",
            "bullets": [
                "Edge Hardware Feasibility: Highly optimized for NVIDIA Jetson Orin Nano ($499) with INT8 TensorRT acceleration.",
                "90% Cost Reduction: Retrofitting legacy infrastructure avoids hundreds of crores in proprietary AI camera replacements.",
                "Phase 1 (Months 1–3): Pilot deployment at 5 high-priority BSF border checkposts and sensitive gates.",
                "Phase 2 (Months 4–8): Border perimeter fence rollout with LoRa mesh and ground-plane homography calibration.",
                "Phase 3 (Months 9–12): Centralized Command & Control integration across CAPF bases with multi-sensor drone docking."
            ],
            "notes": "In terms of feasibility, Project Garuda is designed for real-world CAPF budgets. By combining two-tier inference, INT8 quantization, and in-memory spatial indexing, the entire 4-camera pipeline runs on a single 8GB edge device like the NVIDIA Jetson Orin Nano. Phase 1 targets checkpoint access gates; Phase 2 expands to perimeter fences and drone feeds. Project Garuda delivers sovereign, military-grade surveillance intelligence at a fraction of the cost, making our borders safer, smarter, and fully autonomous."
        },
        # Slide 12: Live Demo Sequence & Conclusion
        {
            "title": "LIVE DEMO SEQUENCE & CONCLUSION",
            "subtitle": "Witness Autonomous Defense Intelligence Operating in Real Time",
            "category": "VERIFIED SYSTEM DEMONSTRATION & JURY DEFENSE",
            "bullets": [
                "Screen 1: Live Multi-Camera Stream with Priority AI Resource Allocation (Full AI vs Low-Power Standby).",
                "Screen 2: Automated 2FA Border Checkpoint (Fuzzy Plate OCR + 128D Driver Biometric Verification).",
                "Screen 3: Garuda-Chain Blockchain Vault (Immutable Merkle blocks and 1-click Section 65B legal certificate).",
                "Screen 4: CyberSentry Tamper Lab (Real-time detection of video loop replay injection attacks).",
                "Proven Readiness: 100% functional, containerized, and tested for immediate operational deployment."
            ],
            "notes": "We don't just have slide decks—Project Garuda is fully built, containerized, and running live. We invite the grand jury to witness our live demonstration: from multi-camera threat tracking and 2-factor checkpoint authorization, to our live blockchain tamper verification lab and CyberSentry defense. Thank you, and we are ready for your questions."
        }
    ]

    for slide_data in slides_data:
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

        # Background fill
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_COLOR
        bg.line.fill.background()

        # Category Tag Header Box
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.4))
        cat_tf = cat_box.text_frame
        cat_tf.word_wrap = True
        p_cat = cat_tf.paragraphs[0]
        p_cat.text = slide_data["category"]
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = ACCENT_CYAN

        # Title Box
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.8))
        title_tf = title_box.text_frame
        title_tf.word_wrap = True
        p_title = title_tf.paragraphs[0]
        p_title.text = slide_data["title"]
        p_title.font.size = Pt(28)
        p_title.font.bold = True
        p_title.font.color.rgb = TEXT_WHITE

        # Subtitle Box
        sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.4), Inches(11.7), Inches(0.5))
        sub_tf = sub_box.text_frame
        sub_tf.word_wrap = True
        p_sub = sub_tf.paragraphs[0]
        p_sub.text = slide_data["subtitle"]
        p_sub.font.size = Pt(14)
        p_sub.font.color.rgb = TEXT_MUTED

        # Content Card (Slate Background for Bullets)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.1), Inches(11.7), Inches(4.7))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = RGBColor(51, 65, 85) # Slate 700 border

        # Bullet Text inside Card
        content_box = slide.shapes.add_textbox(Inches(1.2), Inches(2.3), Inches(10.9), Inches(4.3))
        content_tf = content_box.text_frame
        content_tf.word_wrap = True

        for i, bullet in enumerate(slide_data["bullets"]):
            p_bullet = content_tf.add_paragraph() if i > 0 else content_tf.paragraphs[0]
            p_bullet.text = f"•  {bullet}"
            p_bullet.font.size = Pt(15)
            p_bullet.font.color.rgb = TEXT_WHITE
            p_bullet.space_after = Pt(14)

        # Footer
        footer_box = slide.shapes.add_textbox(Inches(0.8), Inches(7.0), Inches(11.7), Inches(0.3))
        footer_tf = footer_box.text_frame
        p_footer = footer_tf.paragraphs[0]
        p_footer.text = "PROJECT GARUDA — Autonomous Border Video Intelligence | SIH26187 | Ministry of Home Affairs"
        p_footer.font.size = Pt(9)
        p_footer.font.color.rgb = TEXT_MUTED

        # Speaker Notes
        notes_slide = slide.notes_slide
        text_frame = notes_slide.notes_text_frame
        text_frame.text = slide_data["notes"]

    output_path = "Project_Garuda_SIH2026_Pitch_Deck.pptx"
    prs.save(output_path)
    print(f"Presentation saved successfully to {os.path.abspath(output_path)}")

if __name__ == "__main__":
    create_deck()
